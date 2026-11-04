// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// GitHub Pages serves this repo at https://moritzkelber.github.io/orgeldatenbank-bayern/
// so every internal link needs the /orgeldatenbank-bayern/ base path baked in.
export default defineConfig({
  site: 'https://moritzkelber.github.io',
  base: '/orgeldatenbank-bayern',
  integrations: [sitemap()],
});
