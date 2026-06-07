import { useEffect } from "react";

type Props = {
  message: string;
  type: "info" | "error";
  visible: boolean;
  onHide: () => void;
};

export default function Toast({ message, type, visible, onHide }: Props) {
  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(onHide, 3500);
    return () => clearTimeout(t);
  }, [visible, onHide]);

  return (
    <div className={`toast toast--${type} ${!visible ? "toast--hidden" : ""}`}>
      <i className={`ti ti-${type === "info" ? "circle-check" : "alert-triangle"}`} style={{ marginRight: 6 }} />
      {message}
    </div>
  );
}
