import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = {title:'Linkdrop — A link. A video. Yours.',description:'Preview and download videos from public links in available source quality.'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
