'use client';

import Image from 'next/image';
import type { CSSProperties } from 'react';

import type {
  FigureObservation,
  MechanicsImageSelection,
  MechanicsMultimodalResponse,
} from '../../lib/mechanicsMultimodal';

type Props = Readonly<{
  images: readonly MechanicsImageSelection[];
  response: MechanicsMultimodalResponse;
  selectedEvidenceId: string | null;
  onSelectEvidence: (evidenceId: string | null) => void;
}>;

type BBox = Readonly<{ left: number; top: number; right: number; bottom: number }>;
type Point = Readonly<{ x: number; y: number }>;

function finiteUnit(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}

function observationId(observation: FigureObservation): string {
  return String(observation.evidence_id ?? observation.observation_id ?? 'unknown-evidence');
}

function overlayStyle(observation: FigureObservation): CSSProperties | null {
  const region = observation.region;
  if (!region || typeof region !== 'object') return null;
  if (region.kind === 'bbox') {
    const bbox = region.bbox as BBox | undefined;
    const left = finiteUnit(bbox?.left); const top = finiteUnit(bbox?.top);
    const right = finiteUnit(bbox?.right); const bottom = finiteUnit(bbox?.bottom);
    if (left === null || top === null || right === null || bottom === null || right <= left || bottom <= top) return null;
    return { left: `${left * 100}%`, top: `${top * 100}%`, width: `${(right - left) * 100}%`, height: `${(bottom - top) * 100}%` };
  }
  if (region.kind === 'line') {
    const start = region.start as Point | undefined; const end = region.end as Point | undefined;
    const x1 = finiteUnit(start?.x); const y1 = finiteUnit(start?.y);
    const x2 = finiteUnit(end?.x); const y2 = finiteUnit(end?.y);
    if (x1 === null || y1 === null || x2 === null || y2 === null) return null;
    const dx = x2 - x1; const dy = y2 - y1;
    const length = Math.sqrt(dx * dx + dy * dy) * 100;
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;
    return { left: `${x1 * 100}%`, top: `${y1 * 100}%`, width: `${length}%`, height: '8px', transformOrigin: 'left center', transform: `translateY(-4px) rotate(${angle}deg)` };
  }
  if (region.kind === 'polygon' && Array.isArray(region.points)) {
    const points = (region.points as Point[]).map((point) => [finiteUnit(point.x), finiteUnit(point.y)] as const);
    if (points.length < 3 || points.some(([x, y]) => x === null || y === null)) return null;
    const xs = points.map(([x]) => x as number); const ys = points.map(([, y]) => y as number);
    const left = Math.min(...xs); const right = Math.max(...xs); const top = Math.min(...ys); const bottom = Math.max(...ys);
    if (right <= left || bottom <= top) return null;
    const polygon = points.map(([x, y]) => `${(((x as number) - left) / (right - left)) * 100}% ${(((y as number) - top) / (bottom - top)) * 100}%`).join(',');
    return { left: `${left * 100}%`, top: `${top * 100}%`, width: `${(right - left) * 100}%`, height: `${(bottom - top) * 100}%`, clipPath: `polygon(${polygon})` };
  }
  return null;
}

function sourceBadge(observation: FigureObservation): string {
  if (observation.evidence_origin === 'USER_CONFIRMED') return '사용자 확인';
  if (observation.evidence_origin === 'USER_CORRECTED') return '사용자 수정';
  if (String(observation.evidence_origin ?? '').startsWith('FIGURE')) return '그림';
  return '문제 문장';
}

export function MechanicsEvidenceViewer({ images, response, selectedEvidenceId, onSelectEvidence }: Props) {
  if (!images.length || !response.observations.length) return null;
  return (
    <section className="mechanics-evidence-viewer" aria-labelledby="mechanics-evidence-title">
      <h3 id="mechanics-evidence-title">그림 근거 위치</h3>
      <p>근거 항목을 선택하면 그림의 해당 위치가 강조됩니다. 이 표시 자체에는 계산 권한이 없습니다.</p>
      <div className="mechanics-evidence-layout">
        <div className="mechanics-evidence-images">
          {images.map((image, index) => {
            const descriptor = response.sanitized_images.find((item) => item.image_id === image.imageId)
              ?? response.sanitized_images[index];
            const observations = response.observations.filter((item) => item.image_id === descriptor?.image_id || item.image_id === image.imageId);
            const width = descriptor?.width ?? 640; const height = descriptor?.height ?? 420;
            return (
              <div key={image.imageId} className="mechanics-overlay-frame" style={{ aspectRatio: `${width} / ${height}` }}>
                <Image src={image.previewUrl} alt={`문제 그림 ${index + 1}`} fill sizes="(max-width: 760px) 100vw, 50vw" unoptimized className="mechanics-overlay-image" />
                {observations.map((observation) => {
                  const evidenceId = observationId(observation);
                  const style = overlayStyle(observation);
                  if (!style) return null;
                  const selected = evidenceId === selectedEvidenceId;
                  return (
                    <button
                      type="button"
                      key={evidenceId}
                      className={`mechanics-overlay-region${selected ? ' selected' : ''}`}
                      style={style}
                      onClick={() => onSelectEvidence(selected ? null : evidenceId)}
                      aria-label={`${sourceBadge(observation)} 근거 ${String(observation.observed_label ?? observation.observation_kind ?? evidenceId)}`}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
        <ul className="mechanics-evidence-list">
          {response.observations.map((observation) => {
            const evidenceId = observationId(observation);
            return (
              <li key={evidenceId}>
                <button
                  type="button"
                  className={selectedEvidenceId === evidenceId ? 'selected' : ''}
                  onClick={() => onSelectEvidence(selectedEvidenceId === evidenceId ? null : evidenceId)}
                >
                  <span className="chip">{sourceBadge(observation)}</span>
                  <b>{String(observation.observed_label ?? observation.observed_value ?? observation.observation_kind ?? evidenceId)}</b>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
