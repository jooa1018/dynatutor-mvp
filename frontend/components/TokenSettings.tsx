'use client';

import { useState } from 'react';
import { getAccessToken, setAccessToken } from '../lib/api';

type Props = {
  asModal?: boolean;
  message?: string;
  onSaved?: () => void;
  onClose?: () => void;
};

// 개인용 접근 토큰 입력. 일반 카드로도, 401 발생 시 모달로도 쓴다.
// 토큰은 이 기기의 localStorage에만 저장된다 (환경변수/번들 노출 없음).
export default function TokenSettings({ asModal = false, message, onSaved, onClose }: Props) {
  const [value, setValue] = useState(() => (typeof window === 'undefined' ? '' : getAccessToken()));
  const [saved, setSaved] = useState('');

  function save() {
    setAccessToken(value);
    setSaved(value.trim() ? '토큰을 이 기기에 저장했습니다. 다시 시도해 보세요.' : '저장된 토큰을 지웠습니다.');
    onSaved?.();
  }

  const body = (
    <div className="note-card" style={asModal ? { margin: 0 } : undefined}>
      <b>개인용 접근 토큰</b>
      {message ?? '원격 백엔드(Render 등)를 쓰는 경우 서버에 설정한 DYNATUTOR_ACCESS_TOKEN 값을 한 번 저장하세요. 토큰은 이 기기의 브라우저에만 저장됩니다.'}
      <div className="token-row">
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="DYNATUTOR_ACCESS_TOKEN"
          aria-label="개인용 접근 토큰"
        />
        <button className="btn ghost" onClick={save}>토큰 저장</button>
        {asModal && <button className="btn ghost" onClick={onClose}>닫기</button>}
      </div>
      {saved && <p className="notice ok" style={{ marginTop: 10 }}>{saved}</p>}
    </div>
  );

  if (!asModal) return body;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="접근 토큰 필요"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15, 18, 25, 0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, padding: 20,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div style={{ maxWidth: 460, width: '100%' }}>{body}</div>
    </div>
  );
}
