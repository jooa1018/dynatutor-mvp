'use client';

import { useMemo } from 'react';

// 백엔드가 생성한 FBD SVG를 렌더링하기 전에 화이트리스트 기반으로 소독한다.
// (자체 생성 SVG지만, 저장된 record 재표시 등 경로에서 신뢰 경계를 넘을 수
//  있으므로 방어적으로 처리한다.)
const ALLOWED_TAGS = new Set([
  'svg', 'g', 'path', 'line', 'polyline', 'polygon', 'rect', 'circle',
  'ellipse', 'text', 'tspan', 'defs', 'marker', 'title', 'desc',
]);
const ALLOWED_ATTRS = new Set([
  'viewbox', 'width', 'height', 'xmlns', 'fill', 'stroke', 'stroke-width',
  'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'd', 'points',
  'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry',
  'transform', 'font-size', 'font-family', 'text-anchor', 'opacity',
  'marker-end', 'marker-start', 'id', 'refx', 'refy', 'markerwidth',
  'markerheight', 'orient', 'class',
]);

function sanitizeNode(node: Element, doc: Document): Element | null {
  const tag = node.tagName.toLowerCase();
  if (!ALLOWED_TAGS.has(tag)) return null;
  const clean = doc.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const attr of Array.from(node.attributes)) {
    const name = attr.name.toLowerCase();
    const value = attr.value;
    if (!ALLOWED_ATTRS.has(name)) continue;
    if (/javascript:|data:/i.test(value)) continue;
    clean.setAttribute(attr.name, value);
  }
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      clean.appendChild(doc.createTextNode(child.textContent ?? ''));
    } else if (child.nodeType === Node.ELEMENT_NODE) {
      const cleanChild = sanitizeNode(child as Element, doc);
      if (cleanChild) clean.appendChild(cleanChild);
    }
  }
  return clean;
}

export function sanitizeSvg(raw: string): string {
  if (typeof window === 'undefined' || !raw) return '';
  try {
    const doc = new DOMParser().parseFromString(raw, 'image/svg+xml');
    const root = doc.documentElement;
    if (!root || root.tagName.toLowerCase() !== 'svg') return '';
    const clean = sanitizeNode(root, doc);
    return clean ? new XMLSerializer().serializeToString(clean) : '';
  } catch {
    return '';
  }
}

export default function SafeSvg({ svg }: { svg?: string | null }) {
  const cleaned = useMemo(() => sanitizeSvg(svg ?? ''), [svg]);
  if (!cleaned) return <p className="empty">이 유형은 아직 자동 도식이 없습니다.</p>;
  return <div className="svg-box" dangerouslySetInnerHTML={{ __html: cleaned }} />;
}
