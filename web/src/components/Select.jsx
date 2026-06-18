import { useEffect, useRef, useState } from 'react';

function Chevron() {
  return (
    <svg width="10" height="7" viewBox="0 0 10 7" fill="none" aria-hidden="true">
      <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export default function Select({ value, options, onChange, id }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = options.find((item) => item.value === value) || options[0];

  useEffect(() => {
    function handlePointerDown(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, []);

  return (
    <div className="c-select" data-value={value} data-open={open ? 'true' : 'false'} id={id} ref={rootRef}>
      <button type="button" className="c-select-trigger" onClick={() => setOpen((current) => !current)}>
        <span>{selected?.label}</span>
        <Chevron />
      </button>
      <div className="c-select-drop">
        {options.map((item) => (
          <button
            type="button"
            className={`c-select-opt${item.value === value ? ' active' : ''}`}
            data-value={item.value}
            key={item.value}
            onClick={() => {
              onChange(item.value);
              setOpen(false);
            }}
          >
            <span className={`s-dot${item.tone ? ` s-dot-${item.tone}` : ''}`} />
            {item.label}
            <span className="s-c">✓</span>
          </button>
        ))}
      </div>
    </div>
  );
}
