import puppeteer from "puppeteer";
import { writeFileSync } from "node:fs";

// O ícone é desenhado em SVG e fotografado pelo Chrome — sem lib de imagem.
// `margem` é o respiro em volta do desenho: o ícone "maskable" precisa caber
// num círculo, então o desenho encolhe pra dentro da zona segura (80%).
const moto = (traco) => `
  <!-- Rodas menores e mais baixas, pra sobrar laranja entre elas: sem esse
       respiro o corpo encosta nos aros e o desenho vira um borrão. -->
  <circle cx="150" cy="370" r="60" fill="none" stroke="${traco}" stroke-width="30"/>
  <circle cx="366" cy="370" r="60" fill="none" stroke="${traco}" stroke-width="30"/>

  <!-- Rabeta, banco e tanque: uma forma só, apoiada acima das rodas. -->
  <path d="M108 232 L190 236 C216 236 222 210 258 210 L310 210 L336 240
           L336 268 L282 286 L198 286 L152 264 Z" fill="${traco}"/>

  <!-- Balança traseira e garfo dianteiro ligam o corpo às rodas. -->
  <path d="M166 276 L150 352" stroke="${traco}" stroke-width="26" stroke-linecap="round"/>
  <path d="M330 240 L364 340" stroke="${traco}" stroke-width="28" stroke-linecap="round"/>

  <!-- Guidão, preso no topo do garfo: solto no ar ele parecia outra peça. -->
  <path d="M330 236 L340 196 L396 182" fill="none" stroke="${traco}"
        stroke-width="26" stroke-linecap="round" stroke-linejoin="round"/>
`;

const pagina = (escala) => `<!doctype html>
<style>
  html, body { margin: 0; width: 512px; height: 512px; }
  .fundo {
    width: 512px; height: 512px;
    background: linear-gradient(150deg, #e2701f 0%, #c14f15 100%);
    display: grid; place-items: center;
  }
  svg { width: ${512 * escala}px; height: ${512 * escala}px; }
</style>
<div class="fundo">
  <svg viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">${moto("#ffffff")}</svg>
</div>`;

const browser = await puppeteer.launch({ headless: true });

async function gerar(arquivo, lado, escala) {
  const page = await browser.newPage();
  await page.setViewport({ width: 512, height: 512, deviceScaleFactor: lado / 512 });
  await page.setContent(pagina(escala), { waitUntil: "load" });
  const png = await page.screenshot({ type: "png", omitBackground: false });
  writeFileSync(arquivo, png);
  await page.close();
  console.log(`  ${arquivo}  ${lado}x${lado}  ${(png.length / 1024).toFixed(1)} KB`);
}

// "any": o desenho ocupa a arte toda. "maskable": encolhe pra 76%, porque o
// sistema pode recortar o ícone num círculo e comer as bordas.
await gerar("icone-192.png", 192, 1);
await gerar("icone-512.png", 512, 1);
await gerar("icone-maskable-512.png", 512, 0.76);
await gerar("apple-touch-icon.png", 180, 1);
await gerar("preview-48.png", 48, 1);
await browser.close();
