import React from 'react';
import { createRoot } from 'react-dom/client';
import '../styles/globals.css';
import HomeClient from '../components/HomeClient';

const root = document.getElementById('root');
if (!root) {
  throw new Error('DynaTutor root element was not found.');
}

createRoot(root).render(
  <React.StrictMode>
    <HomeClient />
  </React.StrictMode>,
);
