import './globals.css'; import type {Metadata} from 'next'; import {Header} from '@/components/header';
export const metadata:Metadata={title:'IABet',description:'Inteligência estatística para apostas esportivas'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="pt-BR"><body><Header/>{children}</body></html>}
