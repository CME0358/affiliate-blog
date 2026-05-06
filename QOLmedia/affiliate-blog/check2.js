const fs = require('fs');
const path = require('path');
const matter = require('gray-matter');

function collectFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...collectFiles(fullPath));
    else if (entry.name.endsWith('.md') || entry.name.endsWith('.mdx')) files.push(fullPath);
  }
  return files;
}

const dir = path.join(process.cwd(), 'content/posts');
const files = collectFiles(dir);
const posts = files.map(f => {
  const raw = fs.readFileSync(f, 'utf-8');
  const { data } = matter(raw);
  return { category: data.category, published: data.published };
});

const health = posts.filter(p => p.category === '健康');
console.log('健康カテゴリ件数:', health.length);
console.log('サンプル:', health.slice(0, 2));
