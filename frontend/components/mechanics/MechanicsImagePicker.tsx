'use client';

import Image from 'next/image';
import { useEffect, useId, useRef, useState } from 'react';
import type { ChangeEvent, ClipboardEvent, DragEvent } from 'react';

import {
  MECHANICS_IMAGE_LIMITS,
  validateMechanicsImages,
} from '../../lib/mechanicsMultimodal';
import type { MechanicsImageSelection } from '../../lib/mechanicsMultimodal';

type Props = Readonly<{
  value: readonly MechanicsImageSelection[];
  onChange: (value: readonly MechanicsImageSelection[]) => void;
  onError?: (message: string) => void;
  disabled?: boolean;
}>;

function nextImageId(index: number): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `image_${crypto.randomUUID()}`;
  }
  return `image_${Date.now()}_${index}`;
}

export function MechanicsImagePicker({ value, onChange, onError, disabled = false }: Props) {
  const inputId = useId();
  const liveUrls = useRef(new Set<string>());
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    const urlsCreatedByThisComponent = liveUrls.current;
    return () => {
      urlsCreatedByThisComponent.forEach((url) => URL.revokeObjectURL(url));
      urlsCreatedByThisComponent.clear();
    };
  }, []);

  function report(reason: unknown) {
    onError?.(reason instanceof Error ? reason.message : '그림을 추가하지 못했습니다.');
  }

  function createSelection(file: File, index: number): MechanicsImageSelection {
    const previewUrl = URL.createObjectURL(file);
    liveUrls.current.add(previewUrl);
    return { imageId: nextImageId(index), file, previewUrl };
  }

  function appendFiles(files: readonly File[]) {
    if (!files.length || disabled) return;
    try {
      validateMechanicsImages([...value.map((item) => item.file), ...files]);
      const additions = files.map((file, index) => createSelection(file, value.length + index));
      onChange([...value, ...additions]);
    } catch (reason) {
      report(reason);
    }
  }

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    appendFiles(files);
  }

  function removeImage(imageId: string) {
    const removed = value.find((item) => item.imageId === imageId);
    if (removed) {
      URL.revokeObjectURL(removed.previewUrl);
      liveUrls.current.delete(removed.previewUrl);
    }
    onChange(value.filter((item) => item.imageId !== imageId));
  }

  function replaceImage(imageId: string, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || disabled) return;
    const index = value.findIndex((item) => item.imageId === imageId);
    if (index < 0) return;
    try {
      const files = value.map((item, itemIndex) => (itemIndex === index ? file : item.file));
      validateMechanicsImages(files);
      const previous = value[index];
      URL.revokeObjectURL(previous.previewUrl);
      liveUrls.current.delete(previous.previewUrl);
      const replacement = createSelection(file, index);
      onChange(value.map((item, itemIndex) => (itemIndex === index ? replacement : item)));
    } catch (reason) {
      report(reason);
    }
  }

  function dropFiles(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragActive(false);
    appendFiles(Array.from(event.dataTransfer.files));
  }

  function pasteImages(event: ClipboardEvent<HTMLElement>) {
    const files = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith('image/'));
    if (!files.length) return;
    event.preventDefault();
    appendFiles(files);
  }

  return (
    <section aria-labelledby={`${inputId}-title`} className="mechanics-image-picker">
      <div className="field-label" id={`${inputId}-title`}>문제 그림 <i>(선택)</i></div>
      <div
        className={`mechanics-dropzone${dragActive ? ' active' : ''}`}
        onDragEnter={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDragActive(true); }}
        onDragOver={(event: DragEvent<HTMLElement>) => event.preventDefault()}
        onDragLeave={(event: DragEvent<HTMLElement>) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragActive(false);
        }}
        onDrop={dropFiles}
        onPaste={pasteImages}
        role="group"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-describedby={`${inputId}-help`}
      >
        <p id={`${inputId}-help`}>
          그림을 끌어놓거나 붙여넣으세요. PNG·JPEG·WebP, 각 8MB 이하, 최대 {MECHANICS_IMAGE_LIMITS.count}개입니다.
        </p>
        <label htmlFor={inputId} className="mini-btn">
          그림 선택
        </label>
        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept={MECHANICS_IMAGE_LIMITS.mediaTypes.join(',')}
          multiple
          disabled={disabled || value.length >= MECHANICS_IMAGE_LIMITS.count}
          onChange={addFiles}
        />
      </div>

      {value.length > 0 ? (
        <ul className="mechanics-image-grid" aria-label="첨부한 문제 그림">
          {value.map((item, index) => {
            const replaceId = `${inputId}-replace-${index}`;
            return (
              <li key={item.imageId} className="mechanics-image-card">
                <Image
                  src={item.previewUrl}
                  alt={`${item.file.name || `그림 ${index + 1}`} 미리보기`}
                  width={320}
                  height={220}
                  unoptimized
                  className="mechanics-image-preview"
                />
                <p title={item.file.name}>{item.file.name || `그림 ${index + 1}`}</p>
                <div className="mini-actions">
                  <label className="mini-btn" htmlFor={replaceId}>교체</label>
                  <input
                    id={replaceId}
                    className="sr-only"
                    type="file"
                    accept={MECHANICS_IMAGE_LIMITS.mediaTypes.join(',')}
                    disabled={disabled}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => replaceImage(item.imageId, event)}
                  />
                  <button type="button" className="mini-btn" disabled={disabled} onClick={() => removeImage(item.imageId)}>
                    삭제
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
