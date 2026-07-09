# Phase 11: iPhone 14 / PWA Optimization

Phase 11 focuses on using DynaTutor comfortably from an iPhone 14 without turning it into a native iOS app.

## What changed

- iPhone 14 portrait-first layout.
- PWA manifest and Apple touch icon.
- iOS `appleWebApp` metadata.
- `viewport-fit=cover` and CSS safe-area support.
- Bottom thumb navigation for Solve / Study / Examples / Notebook.
- 44px+ touch targets for mobile controls.
- Horizontal chip/tab scrolling on narrow screens.
- Mobile-friendly cards, textareas, math blocks, and diagrams.
- LAN-aware API base URL: when opened from `http://PC-IP:3000`, the frontend calls `http://PC-IP:8000` automatically.
- `scripts/run_iphone_lan.sh` and `scripts/run_iphone_lan_windows.bat`.

## How to use on iPhone 14

1. Connect the computer and iPhone to the same Wi‑Fi.
2. Run:

```bash
./scripts/run_iphone_lan.sh
```

3. Open the shown `http://<PC-IP>:3000` address in iPhone Safari.
4. Tap Share → Add to Home Screen.
5. Launch DynaTutor from the home screen.

## Notes

This is still a local web/PWA workflow, not a native App Store iOS app. The backend still runs on your computer. The iPhone is a comfortable client screen.
