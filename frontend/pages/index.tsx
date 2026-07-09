import Head from 'next/head';
import HomeClient from '../components/HomeClient';

export default function Home() {
  return (
    <>
      <Head>
        <title>DynaTutor</title>
        <meta name="description" content="아이폰14에 최적화한 개인용 동역학 문제풀이 튜터" />
        <meta name="application-name" content="DynaTutor" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
        <meta name="theme-color" content="#FBFBFD" />
        <meta name="format-detection" content="telephone=no" />
        <link rel="manifest" href="/manifest.webmanifest" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
      </Head>
      <HomeClient />
    </>
  );
}
