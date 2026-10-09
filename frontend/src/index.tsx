/* @refresh reload */
import { render } from 'solid-js/web';
import './index.css';
import { App } from './App';

const root = document.getElementById('root');

if (import.meta.env.DEV && !(root instanceof HTMLElement)) {
  throw new Error(
    'Elemento root no encontrado. Asegúrate de que existe en el index.html'
  );
}

render(() => <App />, root!);
