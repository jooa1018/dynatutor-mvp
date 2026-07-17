'use client';

// Phase 54: "동작으로 이해하기" — Rapier2D 기반 동작 시각화 섹션.
// 이 섹션은 표시 전용이다. backend 답(정답 권위)은 answer_overlay로만 보여주고,
// 애니메이션에서 파생된 값은 항상 '애니메이션 근사값'으로 구분해 표시한다.
// 장면이 없거나 깨졌거나 WASM이 실패해도 기존 답/풀이 카드는 영향받지 않는다.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Section } from './Card';
import { validateScene } from '../lib/visualizationScene';
import * as motionLib from '../lib/motionProgram';
import { renderScene } from '../lib/vizRenderer';
import { VizController } from '../lib/vizController';

const SPEEDS: number[] = [0.25, 0.5, 1];

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

function AnswerOverlayPanel({ scene }: { scene: any }) {
  return (
    <div className="viz-values viz-values-backend">
      <p className="col-label">백엔드 계산값 (정답 권위)</p>
      <ul className="list">
        {(scene.answer_overlay || []).map((item: any, i: number) => (
          <li key={i}><code className="math">{item.display || `${item.label}: ${item.numeric ?? '-'} ${item.unit ?? ''}`}</code></li>
        ))}
      </ul>
    </div>
  );
}

function SceneNotes({ scene }: { scene: any }) {
  const rows: Array<[string, string[]]> = [];
  if (scene.assumptions?.length) rows.push(['가정', scene.assumptions]);
  if (scene.schematic_notes?.length) rows.push(['표시용(시각화 전용) 값', scene.schematic_notes]);
  if (scene.warnings?.length) rows.push(['경고', scene.warnings]);
  if (scene.constraints?.length) rows.push(['제약조건', scene.constraints.map((c: any) => c.description)]);
  if (!rows.length) return null;
  return (
    <details className="step viz-notes">
      <summary><span className="step-title">장면 설명 · 가정 · 경고</span></summary>
      {scene.scene_description ? <p className="step-body">{scene.scene_description}</p> : null}
      {rows.map(([label, items]) => (
        <div key={label}>
          <p className="col-label" style={{ marginTop: 8 }}>{label}</p>
          <ul className="list">{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      ))}
      {scene.coordinate_frame?.positive_directions?.length ? (
        <div>
          <p className="col-label" style={{ marginTop: 8 }}>좌표계 (양의 방향)</p>
          <ul className="list">
            {scene.coordinate_frame.positive_directions.map((d: string, i: number) => (
              <li key={i}>{scene.coordinate_frame.axes?.[i] ?? `축${i + 1}`}: {d}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </details>
  );
}

function JsonExportImport({ scene, onImport }: { scene: any; onImport: (s: any) => void }) {
  const [text, setText] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const json = useMemo(() => JSON.stringify(scene, null, 2), [scene]);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(json);
      setMessage('장면 JSON을 복사했습니다.');
    } catch {
      setMessage('클립보드 복사에 실패했습니다. 아래 텍스트를 직접 복사하세요.');
    }
  }, [json]);
  const doImport = useCallback(() => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setMessage('JSON을 해석할 수 없습니다.');
      return;
    }
    const check = validateScene(parsed);
    if (!check.ok) {
      setMessage(`장면 검증 실패: ${check.errors[0]}`);
      return;
    }
    if ((parsed as any).status !== 'ready') {
      setMessage('가져온 장면이 ready 상태가 아닙니다.');
      return;
    }
    setMessage(null);
    onImport(parsed);
  }, [text, onImport]);
  return (
    <details className="step viz-json">
      <summary><span className="step-title">장면 JSON 내보내기 / 가져오기</span></summary>
      <div className="viz-json-actions">
        <button type="button" className="mini-btn viz-touch" onClick={copy}>JSON 복사</button>
        <a
          className="mini-btn viz-touch"
          href={`data:application/json;charset=utf-8,${encodeURIComponent(json)}`}
          download="dynatutor-scene.json"
        >다운로드</a>
      </div>
      <textarea
        className="viz-json-text"
        readOnly
        value={json}
        rows={6}
        aria-label="현재 장면 JSON"
        onFocus={(e) => e.currentTarget.select()}
      />
      <p className="col-label" style={{ marginTop: 10 }}>장면 JSON 가져오기</p>
      <textarea
        className="viz-json-text"
        value={text}
        rows={4}
        placeholder="내보낸 장면 JSON을 붙여넣으세요"
        aria-label="가져올 장면 JSON 입력"
        onChange={(e) => setText(e.target.value)}
      />
      <div className="viz-json-actions">
        <button type="button" className="mini-btn viz-touch" onClick={doImport}>가져오기</button>
      </div>
      {message ? <p className="unsupported" role="status">{message}</p> : null}
    </details>
  );
}

// prefers-reduced-motion: 자동재생/연속 애니메이션 없이 시작·중간·최종 상태를
// 단계식으로 보여준다. Rapier/WASM도 로드하지 않는다.
function ReducedMotionViewer({ scene }: { scene: any }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const times = useMemo(() => motionLib.snapshotTimes(scene), [scene]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cam = scene.camera;
      const aspect = (cam.max_y - cam.min_y) / (cam.max_x - cam.min_x);
      const height = Math.max(160, Math.min(420, Math.round(rect.width * aspect)));
      canvas.style.height = `${height}px`;
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(height * dpr);
      renderScene(canvas, scene, times[index], { showVelocity: true, showAcceleration: true, showForces: true });
    };
    draw();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(draw) : null;
    observer?.observe(canvas);
    return () => observer?.disconnect();
  }, [scene, index, times]);

  const label = motionLib.snapshotLabel(scene, index, times);
  return (
    <div>
      <p className="viz-reduced-note">모션 축소 설정이 감지되어 애니메이션 대신 단계별 상태로 표시합니다.</p>
      <canvas ref={canvasRef} className="viz-canvas" role="img" aria-label={`${scene.scene_label ?? '장면'} — ${label}. ${scene.scene_description ?? ''}`} />
      <div className="viz-controls" role="group" aria-label="단계별 상태 보기">
        <button
          type="button" className="mini-btn viz-touch"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
        >← 이전 상태</button>
        <span className="viz-time" aria-live="polite">{label} ({index + 1}/{times.length})</span>
        <button
          type="button" className="mini-btn viz-touch"
          onClick={() => setIndex((i) => Math.min(times.length - 1, i + 1))}
          disabled={index === times.length - 1}
        >다음 상태 →</button>
      </div>
    </div>
  );
}

function AnimatedViewer({ scene }: { scene: any }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const controllerRef = useRef<VizController | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState(1);
  const [speedLive, setSpeedLive] = useState<number | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [engineReady, setEngineReady] = useState(false);
  const stateRef = useRef({ vx: 0, vy: 0, ax: 0, ay: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let cancelled = false;
    const controller = new VizController(canvas, scene, {
      onFrame: (t, state) => {
        if (cancelled) return;
        setTime(t);
        setPlaying(state.playing);
        const kinematic = (scene.bodies as any[]).find((b) => b.body_type === 'kinematic');
        if (kinematic) {
          const s = motionLib.evaluateBody(scene, kinematic, t);
          stateRef.current = { vx: s.vx, vy: s.vy, ax: s.ax, ay: s.ay };
        }
      },
      onError: (message) => {
        if (!cancelled) setRuntimeError(message);
      },
      onReady: () => {
        if (!cancelled) setEngineReady(true);
      },
    });
    controllerRef.current = controller;
    controller.start();
    return () => {
      cancelled = true;
      controller.dispose();
      controllerRef.current = null;
    };
  }, [scene]);

  const speedControl = useCallback((s: number) => {
    controllerRef.current?.setSpeed(s);
    setSpeedState(s);
    setSpeedLive(s);
  }, []);

  const duration = motionLib.totalDuration(scene);
  const v = Math.hypot(stateRef.current.vx, stateRef.current.vy);
  const a = Math.hypot(stateRef.current.ax, stateRef.current.ay);

  return (
    <div>
      {runtimeError ? (
        <p className="viz-fallback-note" role="status">
          물리 엔진(WASM)을 불러오지 못해 정지 화면으로 표시합니다. 답과 풀이는 위 카드에서 그대로 확인할 수 있습니다.
        </p>
      ) : null}
      <canvas
        ref={canvasRef}
        className="viz-canvas"
        role="img"
        aria-label={`${scene.scene_label ?? '장면'} 애니메이션. ${scene.scene_description ?? ''}`}
      />
      <div className="viz-controls" role="group" aria-label="애니메이션 컨트롤">
        <button
          type="button"
          className="btn primary viz-touch"
          aria-pressed={playing}
          onClick={() => {
            const c = controllerRef.current;
            if (!c) return;
            if (playing) c.pause(); else c.play();
          }}
        >{playing ? '일시정지' : '재생'}</button>
        <button type="button" className="mini-btn viz-touch" onClick={() => controllerRef.current?.reset()}>리셋</button>
        <button
          type="button" className="mini-btn viz-touch"
          onClick={() => controllerRef.current?.stepOnce()}
          aria-label="한 단계 진행 (고정 시간 간격)"
        >한 단계 ▸</button>
        <span className="viz-speed" role="group" aria-label="재생 속도">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className={`mini-btn viz-touch${speed === s ? ' viz-active' : ''}`}
              aria-pressed={speed === s}
              onClick={() => speedControl(s)}
            >{s}×</button>
          ))}
        </span>
        <span className="viz-time" aria-live="off">t = {time.toFixed(2)} s / {duration.toFixed(2)} s</span>
      </div>
      <p className="sr-only" aria-live="polite">
        {speedLive != null ? `재생 속도 ${speedLive}배` : null}
      </p>
      <div className="viz-values viz-values-anim">
        <p className="col-label">애니메이션 근사값 (정답 아님 · 표시 전용)</p>
        <p className="viz-anim-readout">
          <code className="math">|v| ≈ {v.toFixed(2)} m/s</code>{' '}
          <code className="math">|a| ≈ {a.toFixed(2)} m/s²</code>
          {!engineReady && !runtimeError ? <span className="viz-loading"> · 물리 엔진 로딩 중…</span> : null}
        </p>
      </div>
      <p className="viz-legend">
        화살표 구분: <strong>v</strong> 실선+채운 화살촉(속도) · <strong>a</strong> 실선+빈 화살촉(가속도) ·
        힘은 점선+기호 라벨(mg, N, f…) · 충격량 J는 굵은 점선. 모든 화살표에 문자 라벨이 붙습니다.
      </p>
    </div>
  );
}

export default function VisualizationSection({ scene: rawScene }: { scene: any }) {
  const [opened, setOpened] = useState(false);
  const [importedScene, setImportedScene] = useState<any | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  const validation = useMemo(() => (rawScene == null ? null : validateScene(rawScene)), [rawScene]);
  if (rawScene == null) return null;

  if (!validation?.ok) {
    return (
      <Section label="동작으로 이해하기">
        <p className="unsupported">시각화 장면 데이터를 해석할 수 없어 표시하지 않습니다. 답과 풀이는 위 카드에서 그대로 확인할 수 있습니다.</p>
      </Section>
    );
  }

  if (rawScene.status !== 'ready') {
    return (
      <Section label="동작으로 이해하기">
        <p className="unsupported">{rawScene.fallback_reason ?? '이 문제 유형은 아직 동작 시각화를 지원하지 않습니다.'}</p>
      </Section>
    );
  }

  const scene = importedScene ?? rawScene;

  return (
    <Section label="동작으로 이해하기">
      <div className="viz-head">
        <p className="viz-title">{scene.scene_label ?? '장면'}</p>
        <p className="viz-authority">시각화는 근사 표시 전용이며, 정답·채점 권위는 항상 백엔드 계산에 있습니다.</p>
      </div>
      <p className="sr-only">{scene.scene_description}</p>
      {importedScene ? (
        <p className="viz-imported-banner" role="status">
          가져온 장면을 표시 중입니다. 이 장면의 값은 현재 문제의 backend 답이 아닐 수 있습니다.{' '}
          <button type="button" className="mini-btn viz-touch" onClick={() => setImportedScene(null)}>원래 장면으로</button>
        </p>
      ) : null}

      <AnswerOverlayPanel scene={scene} />

      {!opened ? (
        <button type="button" className="btn primary viz-touch viz-open-btn" onClick={() => setOpened(true)}>
          {reducedMotion ? '장면 열기 (단계별 상태 보기)' : '동작 보기 (물리 엔진 로드)'}
        </button>
      ) : reducedMotion ? (
        <ReducedMotionViewer key={importedScene ? 'imported' : 'original'} scene={scene} />
      ) : (
        <AnimatedViewer key={importedScene ? 'imported' : 'original'} scene={scene} />
      )}

      <SceneNotes scene={scene} />
      <JsonExportImport scene={scene} onImport={setImportedScene} />
    </Section>
  );
}
