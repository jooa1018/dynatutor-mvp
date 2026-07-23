"use client";

import { ChangeEvent, useEffect, useId, useRef } from "react";

import {
  MECHANICS_IMAGE_LIMITS,
  MechanicsImageSelection,
  validateMechanicsImages,
} from "../../lib/mechanicsMultimodal";

type Props = Readonly<{
  value: readonly MechanicsImageSelection[];
  onChange: (value: readonly MechanicsImageSelection[]) => void;
  disabled?: boolean;
}>;

function nextImageId(index: number): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `image_${crypto.randomUUID()}`;
  }
  return `image_${Date.now()}_${index}`;
}

export function MechanicsImagePicker({ value, onChange, disabled = false }: Props) {
  const inputId = useId();
  const urls = useRef(new Set<string>());

  useEffect(
    () => () => {
      for (const url of urls.current) URL.revokeObjectURL(url);
      urls.current.clear();
    },
    [],
  );

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    validateMechanicsImages([...value.map((item) => item.file), ...files]);
    const additions = files.map((file, index) => {
      const previewUrl = URL.createObjectURL(file);
      urls.current.add(previewUrl);
      return {
        imageId: nextImageId(value.length + index),
        file,
        previewUrl,
      } satisfies MechanicsImageSelection;
    });
    onChange([...value, ...additions]);
  }

  function removeImage(imageId: string) {
    const removed = value.find((item) => item.imageId === imageId);
    if (removed) {
      URL.revokeObjectURL(removed.previewUrl);
      urls.current.delete(removed.previewUrl);
    }
    onChange(value.filter((item) => item.imageId !== imageId));
  }

  return (
    <section aria-labelledby={`${inputId}-title`} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id={`${inputId}-title`} className="font-semibold">
            문제 그림
          </h3>
          <p className="text-sm text-slate-600">
            PNG·JPEG·WebP, 각 8MB 이하, 최대 {MECHANICS_IMAGE_LIMITS.count}개
          </p>
        </div>
        <label
          htmlFor={inputId}
          className="cursor-pointer rounded-md border px-3 py-2 text-sm font-medium disabled:cursor-not-allowed"
        >
          그림 추가
        </label>
        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept={MECHANICS_IMAGE_LIMITS.mediaTypes.join(",")}
          multiple
          disabled={disabled || value.length >= MECHANICS_IMAGE_LIMITS.count}
          onChange={addFiles}
        />
      </div>

      {value.length > 0 ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {value.map((item) => (
            <li key={item.imageId} className="rounded-md border p-2">
              <img
                src={item.previewUrl}
                alt={`${item.file.name} 미리보기`}
                className="aspect-square w-full rounded object-contain"
              />
              <p className="mt-2 truncate text-xs" title={item.file.name}>
                {item.file.name}
              </p>
              <button
                type="button"
                disabled={disabled}
                onClick={() => removeImage(item.imageId)}
                className="mt-2 text-xs font-medium underline"
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
