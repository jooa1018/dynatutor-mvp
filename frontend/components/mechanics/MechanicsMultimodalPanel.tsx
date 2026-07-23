'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { ApiAuthError } from '../../lib/api';
import {
  confirmMechanicsMultimodalRevision,
  correctMechanicsMultimodalRevision,
  executeMechanicsMultimodalRevision,
  requestMechanicsMultimodalEvidence,
} from '../../lib/mechanicsMultimodal';
import type {
  EvidenceConfirmation,
  MechanicsImageSelection,
  MechanicsMultimodalResponse,
  SourceCorrectionOperation,
} from '../../lib/mechanicsMultimodal';
import { MechanicsCorrectionForm } from './MechanicsCorrectionForm';
import { MechanicsEvidenceConflictPanel } from './MechanicsEvidenceConflictPanel';
import { MechanicsEvidenceViewer } from './MechanicsEvidenceViewer';
import { MechanicsImagePicker } from './MechanicsImagePicker';

type Props = Readonly<{
  problemText: string;
  disabled?: boolean;
  onAuthError: (error: ApiAuthError) => void;
  onVerifiedResult: (response: MechanicsMultimodalResponse) => void;
}>;

const STATUS_LABEL: Record<string, string> = {
  ready: '모델링 완료',
  confirmation_required: '사용자 확인 필요',
  blocked: '안전하게 중단됨',
  validation_rejected: '원문·단위 검증 실패',
  compiler_rejected: '방정식 구성 불가',
  solve_rejected: '검증 가능한 해를 확정하지 못함',
  solved: '독립 검산 완료',
};

function safeNumber(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '-';
}

export function MechanicsMultimodalPanel({
  problemText,
  disabled = false,
  onAuthError,
  onVerifiedResult,
}: Props) {
  const [images, setImages] = useState<readonly MechanicsImageSelection[]>([]);
  const [confirmations, setConfirmations] = useState<readonly EvidenceConfirmation[]>([]);
  const [result, setResult] = useState<MechanicsMultimodalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('입력 준비');
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const previousProblemText = useRef(problemText);

  useEffect(() => {
    if (previousProblemText.current === problemText) return;
    previousProblemText.current = problemText;
    setResult(null);
    setConfirmations([]);
    setSelectedEvidenceId(null);
    setPhase('입력 준비');
    setError(null);
  }, [problemText]);

  const allConflictsConfirmed = useMemo(() => {
    if (!result || result.terminal !== 'confirmation_required') return true;
    return result.conflicts.every((conflict) => confirmations.some((item) => (
      item.conflict_id === conflict.conflict_id
      && item.conflict_fingerprint === conflict.fingerprint
    )));
  }, [confirmations, result]);

  function handleFailure(reason: unknown, fallback: string) {
    if (reason instanceof ApiAuthError) {
      onAuthError(reason);
      return;
    }
    setError(reason instanceof Error ? reason.message : fallback);
  }

  function acceptResponse(response: MechanicsMultimodalResponse) {
    setResult(response);
    setPhase(STATUS_LABEL[response.terminal] ?? response.terminal);
    if (response.terminal !== 'confirmation_required') setConfirmations([]);
    if (response.terminal === 'solved') onVerifiedResult(response);
  }

  function updateImages(next: readonly MechanicsImageSelection[]) {
    setImages(next);
    setResult(null);
    setConfirmations([]);
    setSelectedEvidenceId(null);
    setPhase('입력 준비');
  }

  async function startModeling() {
    if (loading || disabled || (!problemText.trim() && !images.length)) return;
    setLoading(true);
    setError(null);
    setPhase('이미지 전처리 → 단일 AI 모델링 → 근거 검증');
    try {
      acceptResponse(await requestMechanicsMultimodalEvidence(problemText, images));
    } catch (reason) {
      setPhase('요청 실패');
      handleFailure(reason, '글과 그림 근거를 처리하지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function confirmConflicts() {
    if (!result || !allConflictsConfirmed || loading || disabled) return;
    setLoading(true);
    setError(null);
    setPhase('충돌 확인 → 전체 재검증 → deterministic solve');
    try {
      acceptResponse(await confirmMechanicsMultimodalRevision(result, confirmations));
    } catch (reason) {
      handleFailure(reason, '충돌 확인을 적용하지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function applyCorrections(operations: readonly SourceCorrectionOperation[]): Promise<boolean> {
    if (!result) return false;
    setLoading(true);
    setError(null);
    setPhase('수정 적용 → 정규화 → 컴파일 → 계산 → 독립 검산');
    try {
      acceptResponse(await correctMechanicsMultimodalRevision(result, operations));
      return true;
    } catch (reason) {
      handleFailure(reason, '수정 내용을 안전하게 적용하지 못했습니다.');
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function executeRevision() {
    if (!result || loading || disabled) return;
    setLoading(true);
    setError(null);
    setPhase('서버 revision 재검증 → deterministic solve → 독립 검산');
    try {
      acceptResponse(await executeMechanicsMultimodalRevision(result));
    } catch (reason) {
      handleFailure(reason, '서버 revision을 실행하지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }

  const runtime = result?.runtime;
  const verified = result?.verified_answer;

  return (
    <section className="mechanics-multimodal-panel" aria-labelledby="mechanics-multimodal-title">
      <div className="mechanics-panel-heading">
        <div>
          <h2 id="mechanics-multimodal-title">글과 그림으로 풀기</h2>
          <p>그림은 근거로만 해석하고, 계산과 정답 확정은 기존 deterministic engine과 독립 검산이 수행합니다.</p>
        </div>
        {result?.revision_id ? (
          <div className="mechanics-revision" aria-label="현재 해석 revision">
            <b>Revision {result.revision_number ?? 0}</b>
            <small>{result.revision_id}</small>
            <small>유효 시간 약 {result.expires_in_seconds ?? 0}초</small>
          </div>
        ) : null}
      </div>

      <MechanicsImagePicker
        value={images}
        onChange={updateImages}
        onError={setError}
        disabled={disabled || loading}
      />

      <div className="mechanics-progress" role="status" aria-live="polite">
        <b>현재 단계</b><span>{loading ? `${phase}…` : phase}</span>
      </div>

      <div className="actions">
        <button
          type="button"
          className="btn primary"
          disabled={disabled || loading || (!problemText.trim() && !images.length)}
          onClick={startModeling}
        >
          {loading ? '처리 중…' : images.length ? '글+그림 분석하고 풀기' : 'Generic 경로로 분석하고 풀기'}
        </button>
        {result?.revision_id && result.terminal !== 'confirmation_required' ? (
          <button type="button" className="btn ghost" disabled={disabled || loading} onClick={executeRevision}>
            저장된 revision 다시 검증·실행
          </button>
        ) : null}
      </div>

      {result?.terminal === 'confirmation_required' ? (
        <>
          <MechanicsEvidenceConflictPanel
            conflicts={result.conflicts}
            observations={result.observations}
            confirmations={confirmations}
            onChange={(next) => setConfirmations(next)}
            disabled={loading || disabled}
          />
          <button
            type="button"
            className="btn primary"
            disabled={!allConflictsConfirmed || loading || disabled}
            onClick={confirmConflicts}
          >
            선택한 근거로 전체 재검증
          </button>
        </>
      ) : null}

      {result ? (
        <MechanicsEvidenceViewer
          images={images}
          response={result}
          selectedEvidenceId={selectedEvidenceId}
          onSelectEvidence={setSelectedEvidenceId}
        />
      ) : null}

      {result?.draft && result.terminal !== 'confirmation_required' ? (
        <MechanicsCorrectionForm key={result.revision_id ?? result.revision_fingerprint ?? 'draft'} response={result} disabled={disabled || loading} onApply={applyCorrections} />
      ) : null}

      {runtime ? (
        <section className="mechanics-runtime-summary" aria-labelledby="mechanics-runtime-title">
          <h3 id="mechanics-runtime-title">결정론적 계산과 검산</h3>
          <dl>
            <div><dt>컴파일</dt><dd>{runtime.compiler_status ?? '-'}</dd></div>
            <div><dt>방정식 수</dt><dd>{safeNumber(runtime.equation_count)}</dd></div>
            <div><dt>후보해 수</dt><dd>{safeNumber(runtime.candidate_count)}</dd></div>
            <div><dt>검산 상태</dt><dd>{runtime.solve_terminal ?? runtime.terminal ?? '-'}</dd></div>
          </dl>
          {runtime.applied_law_ids?.length ? <p>적용 법칙: {runtime.applied_law_ids.join(', ')}</p> : null}
          {runtime.verification_checks?.length ? (
            <ul>{runtime.verification_checks.map((check) => <li key={`${check.kind}:${check.status}`}>{check.kind}: {check.status}</li>)}</ul>
          ) : null}
        </section>
      ) : null}

      {result?.terminal === 'solved' && verified ? (
        <section className="mechanics-verified-result" aria-labelledby="mechanics-answer-title">
          <h3 id="mechanics-answer-title">검증된 결과</h3>
          <p className="mechanics-answer-value">{String(verified.value_si ?? '-')} <small>SI</small></p>
          <p>대상 기호: {String(verified.query_symbol_id ?? '-')} · backend: {String(verified.backend ?? '-')}</p>
          {result.corrections_applied.length ? <p>사용자 수정 {result.corrections_applied.length}개를 반영해 처음부터 다시 검증했습니다.</p> : null}
        </section>
      ) : null}

      {result && result.terminal !== 'solved' && result.terminal !== 'confirmation_required' ? (
        <p className="notice err" role="status">
          {STATUS_LABEL[result.terminal] ?? result.terminal}. 미검산 답은 표시하지 않습니다.
        </p>
      ) : null}

      {error ? <p role="alert" className="notice err">{error}</p> : null}
    </section>
  );
}
