import { X } from 'lucide-react';

interface Props {
  title: string;
  body: string;
  onClose: () => void;
}

/** 약관 상세 모달 — 동의 항목 텍스트 클릭 시 열린다 */
export default function TermsModal({ title, body, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-[720px] flex-col gap-6 rounded-card bg-surface p-12"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-6">
          <h2 className="text-[26px] font-bold tracking-[-0.025em]">{title}</h2>
          <button aria-label="닫기" onClick={onClose} className="rounded-[9px] bg-canvas p-2 text-muted">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-auto whitespace-pre-wrap text-[17px] leading-[30px] text-[#3F4A43]">
          {body}
        </div>
        <button
          onClick={onClose}
          className="self-end rounded-field bg-lime px-8 py-4 text-[17px] font-bold text-navy"
        >
          확인했어요
        </button>
      </div>
    </div>
  );
}
