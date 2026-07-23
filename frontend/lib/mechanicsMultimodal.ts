export const MECHANICS_IMAGE_LIMITS = Object.freeze({
  count: 4,
  bytesPerImage: 8 * 1024 * 1024,
  totalBytes: 20 * 1024 * 1024,
  mediaTypes: ["image/png", "image/jpeg", "image/webp"] as const,
});

export type MechanicsImageMediaType =
  (typeof MECHANICS_IMAGE_LIMITS.mediaTypes)[number];

export type MechanicsImageSelection = Readonly<{
  imageId: string;
  file: File;
  previewUrl: string;
}>;

export type EvidenceConflict = Readonly<{
  conflict_id: string;
  fingerprint: string;
  semantic_target_key: string;
  candidate_source_ids: readonly string[];
  candidate_fingerprints: readonly string[];
}>;

export type EvidenceConfirmation = Readonly<{
  conflict_id: string;
  conflict_fingerprint: string;
  chosen_source_id: string;
  chosen_candidate_fingerprint: string;
}>;

export type MechanicsMultimodalResponse = Readonly<{
  schema: "dynatutor.mechanics_multimodal_response";
  version: "1.0";
  terminal: "ready" | "confirmation_required" | "blocked";
  sanitized_images: readonly Readonly<{
    image_id: string;
    image_index: number;
    content_sha256: string;
    width: number;
    height: number;
    media_type: "image/png";
  }>[];
  conflicts: readonly EvidenceConflict[];
  observations: readonly Record<string, unknown>[];
  diagnostics: readonly string[];
  revision_id: string | null;
  revision_fingerprint: string | null;
  draft: Record<string, unknown> | null;
}>;

function asBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
    reader.onload = () => {
      const value = reader.result;
      if (typeof value !== "string") {
        reject(new Error("이미지를 읽지 못했습니다."));
        return;
      }
      const comma = value.indexOf(",");
      if (comma < 0) {
        reject(new Error("이미지 인코딩이 올바르지 않습니다."));
        return;
      }
      resolve(value.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function validateMechanicsImages(files: readonly File[]): void {
  if (files.length > MECHANICS_IMAGE_LIMITS.count) {
    throw new Error(`그림은 최대 ${MECHANICS_IMAGE_LIMITS.count}개까지 첨부할 수 있습니다.`);
  }
  let total = 0;
  for (const file of files) {
    if (!MECHANICS_IMAGE_LIMITS.mediaTypes.includes(file.type as MechanicsImageMediaType)) {
      throw new Error("PNG, JPEG, WebP 그림만 첨부할 수 있습니다.");
    }
    if (file.size <= 0 || file.size > MECHANICS_IMAGE_LIMITS.bytesPerImage) {
      throw new Error("각 그림은 8MB 이하여야 합니다.");
    }
    total += file.size;
  }
  if (total > MECHANICS_IMAGE_LIMITS.totalBytes) {
    throw new Error("첨부 그림의 전체 크기는 20MB 이하여야 합니다.");
  }
}

export async function buildMechanicsMultimodalRequest(
  problemText: string,
  selections: readonly MechanicsImageSelection[],
  confirmations: readonly EvidenceConfirmation[] = [],
): Promise<Record<string, unknown>> {
  const files = selections.map((item) => item.file);
  validateMechanicsImages(files);
  const images = await Promise.all(
    selections.map(async (item) => ({
      image_id: item.imageId,
      media_type: item.file.type,
      data_base64: await asBase64(item.file),
    })),
  );
  return {
    problem_text: problemText,
    images,
    confirmations,
  };
}

export async function requestMechanicsMultimodalEvidence(
  endpoint: string,
  problemText: string,
  selections: readonly MechanicsImageSelection[],
  confirmations: readonly EvidenceConfirmation[] = [],
  signal?: AbortSignal,
): Promise<MechanicsMultimodalResponse> {
  const body = await buildMechanicsMultimodalRequest(
    problemText,
    selections,
    confirmations,
  );
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: { message?: string } }
      | null;
    throw new Error(payload?.detail?.message ?? "그림 근거를 처리하지 못했습니다.");
  }
  return (await response.json()) as MechanicsMultimodalResponse;
}
