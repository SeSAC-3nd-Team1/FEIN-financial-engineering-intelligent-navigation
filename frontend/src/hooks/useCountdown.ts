import { useEffect, useRef, useState } from 'react';

/**
 * 5분(300초) 카운트다운.
 * 남은 시간을 매초 세는 대신 만료 시각(deadline)에서 역산하므로,
 * 탭이 백그라운드로 내려가도 타이머가 밀리지 않는다.
 */
export function useCountdown(seconds = 300) {
  const [remaining, setRemaining] = useState(0);
  const deadline = useRef<number | null>(null);

  const start = () => {
    deadline.current = Date.now() + seconds * 1000;
    setRemaining(seconds);
  };
  const stop = () => {
    deadline.current = null;
    setRemaining(0);
  };

  useEffect(() => {
    if (remaining <= 0) return;
    const id = window.setInterval(() => {
      if (deadline.current === null) return;
      setRemaining(Math.max(0, Math.round((deadline.current - Date.now()) / 1000)));
    }, 250);
    return () => window.clearInterval(id);
  }, [remaining > 0]);

  const label = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;
  return { remaining, label, running: remaining > 0, start, stop };
}
