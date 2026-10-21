import * as THREE from 'three';
import { createPlanetVisual, planetAppearance } from '../src/planetVisuals';
import { planetColor, type Planet } from '../src/galaxyModel';

// A standalone local design study. It never reads or creates workspace datasets.
const sample: Planet = {
  id: 'design-study', group_id: '', parent_id: null, name: 'Sample.csv', sheet: '',
  version: 1, created_at: '', rows: 8, column_count: 6,
  lifecycle: 'ACTIVE', available: true, status: 'READY', operation: 'import',
};
const kinds = [
  { id: 'bands', title: '条带', detail: '柔和的纬向纹理' },
  { id: 'clouds', title: '云纹', detail: '流动的大理石花纹' },
  { id: 'continents', title: '陆块', detail: '不规则的深浅区域' },
  { id: 'craters', title: '陨坑', detail: '细密的凹陷与环形边缘' },
];
const operations = [
  { id: 'import', title: '原始导入', detail: '金色' },
  { id: 'regex_replace', title: '正则替换', detail: '紫色' },
  { id: 'date_normalize', title: '日期统一', detail: '青色' },
  { id: 'categorize', title: '分类整理', detail: '橙色' },
];
const families = new Map<string, string>();
for (let index = 0; families.size < kinds.length && index < 1000; index++) {
  const groupId = `planet-comparison-family-${index}`;
  const { kind } = planetAppearance({ ...sample, group_id: groupId });
  if (!families.has(kind)) families.set(kind, groupId);
}
if (families.size !== kinds.length) throw new Error('Missing comparison texture');

const grid = document.querySelector<HTMLDivElement>('#comparison')!;
grid.append(document.createElement('div'));
for (const kind of kinds) {
  const heading = document.createElement('div');
  heading.className = 'heading';
  heading.textContent = kind.title;
  const detail = document.createElement('small');
  detail.textContent = kind.detail;
  heading.append(detail);
  grid.append(heading);
}

// One temporary renderer produces all sixteen static views, avoiding sixteen WebGL contexts.
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setSize(400, 400);
renderer.setClearColor('#080d18', 0);
const camera = new THREE.PerspectiveCamera(35, 1, 1, 1000);
camera.position.set(0, 0, 150);
camera.lookAt(0, 0, 0);

for (const [row, operation] of operations.entries()) {
  const rowLabel = document.createElement('div');
  rowLabel.className = 'row-label';
  rowLabel.textContent = operation.title;
  const detail = document.createElement('span');
  detail.textContent = operation.detail;
  rowLabel.append(detail);
  grid.append(rowLabel);
  for (const kind of kinds) {
    const node: Planet = {
      ...sample, group_id: families.get(kind.id), version: row + 1,
      parent_id: row ? 'design-source' : null, operation: operation.id,
    };
    rowLabel.style.color = planetColor(node);
    const scene = new THREE.Scene();
    const sun = new THREE.DirectionalLight('#fff0da', 3);
    sun.position.set(120, 100, 160);
    scene.add(new THREE.AmbientLight('#bccff0', .45), sun);
    const visual = createPlanetVisual(node);
    // The grid provides labels; hide only the renderer's version caption.
    for (const child of visual.group.children) {
      if (child instanceof THREE.Sprite && child.position.y < 0) child.visible = false;
    }
    scene.add(visual.group);
    renderer.render(scene, camera);
    const figure = document.createElement('figure');
    figure.className = 'planet';
    const image = document.createElement('img');
    image.alt = `${kind.title} ${operation.title} ${operation.detail}`;
    image.src = renderer.domElement.toDataURL('image/png');
    figure.append(image);
    grid.append(figure);
    visual.resources.forEach(resource => resource.dispose());
  }
}
renderer.dispose();

// A full-resolution contact sheet remains readable outside the narrow preview panel.
await Promise.all(Array.from(grid.querySelectorAll('img'), image => image.decode()));
const sheet = document.createElement('canvas');
sheet.width = 1800; sheet.height = 1500;
const ctx = sheet.getContext('2d')!;
ctx.fillStyle = '#080d18'; ctx.fillRect(0, 0, sheet.width, sheet.height);
ctx.fillStyle = '#e4e9f2'; ctx.font = '500 38px sans-serif';
ctx.fillText('四种花纹，四种操作颜色', 60, 75);
ctx.fillStyle = '#96a6bf'; ctx.font = '22px sans-serif';
ctx.fillText('横向比较花纹 · 纵向比较同一文件的操作颜色', 60, 120);
ctx.textAlign = 'center';
kinds.forEach((kind, column) => {
  ctx.fillStyle = '#e4e9f2'; ctx.font = '28px sans-serif';
  ctx.fillText(kind.title, 420 + column * 370, 200);
  ctx.fillStyle = '#96a6bf'; ctx.font = '19px sans-serif';
  ctx.fillText(kind.detail, 420 + column * 370, 236);
});
const images = Array.from(grid.querySelectorAll('img'));
operations.forEach((operation, row) => {
  const top = 265 + row * 285;
  ctx.strokeStyle = '#ffffff12'; ctx.beginPath(); ctx.moveTo(60, top); ctx.lineTo(1740, top); ctx.stroke();
  ctx.textAlign = 'left'; ctx.font = '26px sans-serif';
  ctx.fillStyle = planetColor({ ...sample, operation: operation.id });
  ctx.fillText(operation.title, 60, top + 135);
  ctx.font = '20px sans-serif'; ctx.fillStyle = '#96a6bf';
  ctx.fillText(operation.detail, 60, top + 173);
  kinds.forEach((_, column) => ctx.drawImage(images[row * 4 + column], 280 + column * 370, top, 280, 280));
});
ctx.fillStyle = '#96a6bf'; ctx.font = '21px sans-serif';
ctx.fillText('真实材质与光照 · 原始版本稍大并带星环 · 本地预览，尚未发布', 60, 1460);
const overview = document.createElement('img');
overview.className = 'overview';
overview.alt = '星球对比图：四列为条带、云纹、陆块、陨坑，四行为金色原始导入、紫色正则替换、青色日期统一、橙色分类整理';
overview.src = sheet.toDataURL('image/png');
grid.hidden = true;
grid.style.display = 'none';
grid.after(overview);
const download = document.createElement('a');
download.className = 'download'; download.href = overview.src;
download.download = 'patternworks-planet-comparison.png';
download.textContent = '下载完整对比图';
overview.after(download);
