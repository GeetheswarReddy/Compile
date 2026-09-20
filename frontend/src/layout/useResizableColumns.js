import { useCallback, useRef, useState } from 'react';

const MIN_LEFT_PERCENT = 35;
const MAX_LEFT_PERCENT = 60;

function clamp(value) {
  return Math.min(MAX_LEFT_PERCENT, Math.max(MIN_LEFT_PERCENT, value));
}

function storedPercent(storageKey, fallback) {
  try {
    const stored = Number(window.localStorage.getItem(storageKey));
    return Number.isFinite(stored) && stored >= MIN_LEFT_PERCENT && stored <= MAX_LEFT_PERCENT
      ? stored
      : fallback;
  } catch {
    return fallback;
  }
}

export function useResizableColumns(storageKey, initialPercent = 45) {
  const containerRef = useRef(null);
  const draggingRef = useRef(false);
  const [leftPercent, setLeftPercent] = useState(() => storedPercent(storageKey, initialPercent));

  const update = useCallback((nextPercent) => {
    const next = Math.round(clamp(nextPercent));
    setLeftPercent(next);
    try {
      window.localStorage.setItem(storageKey, String(next));
    } catch {
      // Resizing still works when storage is unavailable.
    }
  }, [storageKey]);

  const updateFromPointer = useCallback((clientX) => {
    const bounds = containerRef.current?.getBoundingClientRect();
    if (!bounds?.width) return;
    update(((clientX - bounds.left) / bounds.width) * 100);
  }, [update]);

  const separatorProps = {
    role: 'separator',
    'aria-label': 'Resize question and editor panes',
    'aria-orientation': 'vertical',
    'aria-valuemin': MIN_LEFT_PERCENT,
    'aria-valuemax': MAX_LEFT_PERCENT,
    'aria-valuenow': leftPercent,
    tabIndex: 0,
    onPointerDown: (event) => {
      draggingRef.current = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      updateFromPointer(event.clientX);
    },
    onPointerMove: (event) => {
      if (draggingRef.current) updateFromPointer(event.clientX);
    },
    onPointerUp: (event) => {
      draggingRef.current = false;
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    },
    onPointerCancel: () => { draggingRef.current = false; },
    onKeyDown: (event) => {
      const direction = event.key === 'ArrowLeft' ? -5 : event.key === 'ArrowRight' ? 5 : 0;
      if (direction) {
        event.preventDefault();
        update(leftPercent + direction);
      } else if (event.key === 'Home') {
        event.preventDefault();
        update(MIN_LEFT_PERCENT);
      } else if (event.key === 'End') {
        event.preventDefault();
        update(MAX_LEFT_PERCENT);
      }
    },
  };

  return {
    containerRef,
    containerStyle: { '--workspace-left': `${leftPercent}%` },
    separatorProps,
  };
}

export { MIN_LEFT_PERCENT, MAX_LEFT_PERCENT };
