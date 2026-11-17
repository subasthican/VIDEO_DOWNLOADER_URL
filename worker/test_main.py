"""Service integration checks without contacting a video platform."""
import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import httpx

os.environ['VIDEO_WORKER_SECRET'] = 'test-secret-for-service-integration-only'
os.environ.pop('WORKER_PUBLIC_URL', None)
import main as worker


class WorkerFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=worker.app),
            base_url='https://website.example',
        )
        self.headers = {'Authorization': 'Bearer ' + worker.SECRET}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_signed_download_streams_and_cleans_up_on_same_domain(self):
        folders = []

        async def extractor(args, timeout=45):
            if '--dump-single-json' in args:
                return json.dumps({
                    'title': 'Service integration video', 'duration': 5,
                    'formats': [{'height': 360, 'vcodec': 'h264', 'acodec': 'aac',
                                 'ext': 'mp4', 'protocol': 'https',
                                 'url': 'https://media.example/video.mp4'}],
                }).encode()
            output = Path(args[args.index('--output') + 1].replace('%(ext)s', 'mp4'))
            folders.append(output.parent)
            output.write_bytes(b'test-video-response')
            return b''

        with patch.object(worker, 'run', side_effect=extractor):
            analysis = await self.client.post('/analyze', headers=self.headers,
                json={'url': 'https://www.youtube.com/watch?v=example'})
            self.assertEqual(analysis.status_code, 200)
            ticket = await self.client.post('/download', headers=self.headers,
                json={'token': analysis.json()['token'], 'quality': '360'})
            self.assertEqual(ticket.status_code, 200)
            url = ticket.json()['url']
            self.assertTrue(url.startswith('/file/'), url)
            response = await self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'test-video-response')
        self.assertIn('attachment', response.headers['content-disposition'])
        self.assertTrue(folders)
        self.assertTrue(all(not folder.exists() for folder in folders))

    async def test_metadata_requires_shared_secret(self):
        response = await self.client.post('/analyze',
            json={'url': 'https://www.youtube.com/watch?v=example'})
        self.assertEqual(response.status_code, 401)

    async def test_unlimited_duration_accepts_nine_hours_and_longer(self):
        for duration in (34019, 90000):
            with self.subTest(duration=duration), patch.object(worker, 'MAX_DURATION', 0), \
                 patch.object(worker, 'run', return_value=json.dumps({
                     'title': 'Long video', 'duration': duration, 'is_live': False,
                     'formats': [{'height': 720, 'vcodec': 'h264'}],
                 }).encode()):
                response = await self.client.post('/analyze', headers=self.headers,
                    json={'url': 'https://youtu.be/7iCczf3fHWY'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['duration'], duration)
                self.assertIn('720', [f['id'] for f in response.json()['formats']])

    async def test_configured_duration_limit_is_still_enforced(self):
        with patch.object(worker, 'MAX_DURATION', 1800), \
             patch.object(worker, 'run', return_value=b'{"duration":34019}'):
            response = await self.client.post('/analyze', headers=self.headers,
                json={'url': 'https://youtu.be/7iCczf3fHWY'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('30-minute', response.json()['detail'])

    async def test_unlimited_duration_still_rejects_live_and_upcoming_videos(self):
        for metadata in ({'is_live': True}, {'live_status': 'is_upcoming'}):
            with self.subTest(metadata=metadata), patch.object(worker, 'MAX_DURATION', 0), \
                 patch.object(worker, 'run', return_value=json.dumps(metadata).encode()):
                response = await self.client.post('/analyze', headers=self.headers,
                    json={'url': 'https://youtu.be/7iCczf3fHWY'})
                self.assertEqual(response.status_code, 422)
                self.assertIn('finished video', response.json()['detail'])

    async def test_large_file_limits_and_timeout_are_configurable(self):
        # Sparse files exercise the old 500 MB boundary without allocating or streaming it.
        ticket = worker.sign({'url': 'https://youtu.be/7iCczf3fHWY',
                              'quality': '720', 'kind': 'file'})
        for limit, expected_status in ((0, 200), (500, 413)):
            folders = []

            async def extractor(args, timeout=45):
                self.assertEqual(timeout, 86400)
                if limit:
                    self.assertEqual(args[args.index('--max-filesize') + 1], '500M')
                else:
                    self.assertNotIn('--max-filesize', args)
                output = Path(args[args.index('--output') + 1].replace('%(ext)s', 'mp4'))
                folders.append(output.parent)
                with output.open('wb') as video:
                    video.truncate(501 * 1024 * 1024)
                return b''

            with self.subTest(limit=limit), patch.object(worker, 'MAX_FILESIZE_MB', limit), \
                 patch.object(worker, 'DOWNLOAD_TIMEOUT', 86400), \
                 patch.object(worker, 'run', side_effect=extractor):
                if expected_status == 200:
                    response = await worker.file(ticket)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.path.stat().st_size, 501 * 1024 * 1024)
                    await response.background()
                else:
                    with self.assertRaises(worker.HTTPException) as error:
                        await worker.file(ticket)
                    self.assertEqual(error.exception.status_code, expected_status)
            self.assertTrue(folders)
            self.assertTrue(all(not folder.exists() for folder in folders))

    async def test_tampered_file_ticket_is_rejected(self):
        response = await self.client.get('/file/not-a-valid-ticket')
        self.assertEqual(response.status_code, 410)

    async def test_platform_bot_challenge_is_reported_and_logged_without_urls(self):
        process = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(
            b'', b"ERROR: Sign in to confirm you're not a bot. https://example.com/?token=private")))
        with patch.object(asyncio, 'create_subprocess_exec', return_value=process), \
             self.assertLogs('linkdrop.extractor', level='WARNING') as logs:
            response = await self.client.post('/analyze', headers=self.headers,
                json={'url': 'https://www.youtube.com/watch?v=example'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('blocking automated requests', response.json()['detail'])
        self.assertNotIn('token=private', ''.join(logs.output))

    async def test_busy_worker_returns_timeout_instead_of_waiting_indefinitely(self):
        ticket = worker.sign({'url': 'https://www.youtube.com/watch?v=example',
                              'quality': '360', 'kind': 'file'})
        with patch.object(worker, 'slots', asyncio.Semaphore(0)), \
             patch.object(worker, 'DOWNLOAD_TIMEOUT', 0.01):
            response = await self.client.get('/file/' + ticket)
        self.assertEqual(response.status_code, 504)


if __name__ == '__main__':
    unittest.main()
