import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// `fileURLToPath`, а не `new URL(...).pathname`: на Windows тот отдаёт
// `/D:/Projects/Python%20Scripts/...` — с косой перед буквой диска и
// процентными пробелами, — и достроенный путь ведёт в никуда. Ввоз по
// псевдониму упал бы на первом же экране.
const here = dirname(fileURLToPath(import.meta.url));

// Псевдонимы задвоены нарочно: этот перечень читает сборщик, а такой же —
// проверка границ слоёв в `.claude/clean.json`. Проверка чужих сборщиков не
// понимает, а без псевдонимов не видит, куда ведёт ввоз, и пропускает ввоз
// вверх по слоям. Разъедутся перечни — проверка замолчит, поэтому они рядом.
const layers = {
  $api: 'api',
  $app: 'app',
  $components: 'components',
  $state: 'state',
  $styles: 'styles',
};

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: Object.fromEntries(
      Object.entries(layers).map(([name, folder]) => [name, resolve(here, folder)]),
    ),
  },
  // Раздаёт собранное окно, а не сервер разработки: пути внутри страницы
  // относительные, потому что окно открывает её с корня своей раздачи.
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    // `node`, а не браузер: проверяется вынесенная из разметки логика и
    // обёртка моста, а моста в браузере всё равно нет — он подделывается.
    environment: 'node',
    include: ['tests/**/*.test.js'],
    // Пояс прогона задан нарочно. Мост отдаёт время с поясом, а окно рисует
    // его местными часами — то есть перевод из одного в другой и есть предмет
    // проверки. Оставь пояс машинным, и та же проверка на разных машинах
    // ждала бы разного, а на UTC не проверяла бы вовсе ничего.
    env: { TZ: 'Europe/Moscow' },
  },
});
