# Phase 2 Notes

## 이번 단계의 목표

Phase 1이 “구조 뼈대”였다면, Phase 2는 “실제로 더 많은 대표 문제를 풀 수 있는 학습 MVP”입니다.

## 추가된 solver

- `constant_acceleration_1d`
- `projectile_motion`
- `constant_force_work`
- `fixed_axis_rotation`
- `impulse_momentum`
- `collision_1d` 반발계수 확장

## 설계 원칙

1. 기존 앱의 규칙은 최종 판단자가 아니라 hint로만 사용한다.
2. 실제 계산은 solver registry에서 선택된 solver가 한다.
3. 검산과 주의사항은 UI에 그대로 노출한다.
4. 모르는 문제는 억지로 풀지 않고 부족한 정보를 알려준다.

## 아직 일부러 남겨둔 한계

- 포물선 solver는 기본적으로 같은 높이 착지를 가정한다.
- 등가속도 solver는 자연어 파싱이 아직 제한적이다.
- 오답노트는 로컬 SQLite라 사용자 인증/동기화는 없다.
- FBD는 아직 그림이 아니라 텍스트 카드다.
- PyDy는 아직 직접 호출하지 않는다.
