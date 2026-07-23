"use client";

import { FormEvent, useMemo, useState } from "react";

import {
  EvidenceConfirmation,
  MechanicsImageSelection,
  MechanicsMultimodalResponse,
  requestMechanicsMultimodalEvidence,
} from "../../lib/mechanicsMultimodal";
import { MechanicsEvidenceConflictPanel } from "./MechanicsEvidenceConflictPanel";
import { MechanicsImagePicker } from "./MechanicsImagePicker";

type Props = Readonly<{
  endpoint?: string;
  initialProblemText?: string;
  onReadyDraft: (draft: Record<string, unknown>) => void;
}>;

export function MechanicsMultimodalPanel({
  endpoint = "/api/mechanics/multimodal/evidence",
  initialProblemText = "",
  onReadyDraft,
}: Props) {
  const [problemText, setProblemText] = useState(initialProblemText);
  const [images, setImages] = useState<readonly MechanicsImageSelection[]>([]);
  const [confirmations, setConfirmations] = useState<
    readonly EvidenceConfirmation[]
  >([]);
  const [result, setResult] = useState<MechanicsMultimodalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const allConflictsConfirmed = useMemo(() => {
    if (!result || result.terminal !== "confirmation_required") return true;
    return result.conflicts.every((conflict) =>
      confirmations.some(
        (item) =>
          item.conflict_id === conflict.conflict_id &&
          item.conflict_fingerprint === conflict.fingerprint,
      ),
    );
  }, [confirmations, result]);

  function updateImages(next: readonly MechanicsImageSelection[]) {
    setImages(next);
    setResult(null);
    setConfirmations([]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!problemText.trim() || loading || !allConflictsConfirmed) return;
    setLoading(true);
    setError(null);
    try {
      const response = await requestMechanicsMultimodalEvidence(
        endpoint,
        problemText.trim(),
        images,
        confirmations,
      );
      setResult(response);
      if (response.terminal === "ready" && response.draft) {
        onReadyDraft(response.draft);
      }
      if (response.terminal !== "confirmation_required") {
        setConfirmations([]);
      }
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "그림 근거를 처리하지 못했습니다.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <label className="block space-y-2">
        <span className="font-semibold">문제 글</span>
        <textarea
          value={problemText}
          onChange={(event) => {
            setProblemText(event.target.value);
            setResult(null);
            setConfirmations([]);
          }}
          rows={7}
          maxLength={30000}
          required
          disabled={loading}
          className="w-full rounded-md border p-3"
          placeholder="문제의 문장을 입력해 주세요. 그림만 올리지 말고, 보이는 글도 함께 적어 주세요."
        />
      </label>

      <MechanicsImagePicker
        value={images}
        onChange={updateImages}
        disabled={loading}
      />

      {result?.terminal === "confirmation_required" ? (
        <MechanicsEvidenceConflictPanel
          conflicts={result.conflicts}
          confirmations={confirmations}
          onChange={setConfirmations}
          disabled={loading}
        />
      ) : null}

      {result?.terminal === "blocked" ? (
        <p role="status" className="rounded-md border p-3 text-sm">
          근거를 안전하게 확정하지 못했습니다. 문제 글이나 그림을 확인해 주세요.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-md border p-3 text-sm">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={loading || !problemText.trim() || !allConflictsConfirmed}
        className="rounded-md border px-4 py-2 font-semibold disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading
          ? "확인 중…"
          : result?.terminal === "confirmation_required"
            ? "선택한 근거로 다시 확인"
            : "글과 그림 근거 확인"}
      </button>
    </form>
  );
}
