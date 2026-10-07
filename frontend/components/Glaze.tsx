import { useId, type HTMLAttributes, type Ref } from "react";

export interface GlazeProps extends HTMLAttributes<HTMLElement> {
  as?: "div" | "section" | "header" | "footer" | "aside" | "nav" | "main";
  variant?: "panel" | "strip" | "slab";
  lens?: boolean;
  backdrop?: boolean;
  fur?: boolean;
  ref?: Ref<HTMLElement>;
}

/** Framework glaze only. The lens and blur are siblings, never backdrop ancestors. */
export default function Glaze({as="div", variant="panel", lens=true, backdrop=true, fur=false, className="", children, ref, ...props}: GlazeProps) {
  const id = useId().replace(/:/g, "");
  const Tag = as as "div";
  return <Tag {...props} ref={ref as Ref<HTMLDivElement>} className={`glaze glaze-${variant} ${className}`}>
    {backdrop && lens && <span key="lens" aria-hidden="true" className="glaze-layer glaze-lens" />}
    {backdrop && <span key="blur" aria-hidden="true" className="glaze-layer glaze-blur" />}
    <span key="tint" aria-hidden="true" className="glaze-layer glaze-tint" />
    {fur && <svg key="fur" aria-hidden="true" className="glaze-layer glaze-fur" preserveAspectRatio="none" viewBox="0 0 328 170">
      <defs>
        <pattern id={`${id}-fur`} width="61" height="170" patternUnits="userSpaceOnUse" fill="var(--fur)">
          <path d="M8 4 h1 L8.9 132 Z" fillOpacity=".9"/><path d="M27 9 h.8 L27.4 98 Z" fillOpacity=".7"/><path d="M44 3 h1.1 L44.2 152 Z"/><path d="M55.5 12 h.7 L55.9 72 Z" fillOpacity=".6"/>
        </pattern>
        <linearGradient id={`${id}-fade`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="white"/><stop offset=".55" stopColor="white" stopOpacity=".7"/><stop offset="1" stopColor="white" stopOpacity="0"/></linearGradient>
        <mask id={`${id}-mask`}><rect width="328" height="170" fill={`url(#${id}-fade)`}/></mask>
      </defs>
      <rect width="328" height="170" fill={`url(#${id}-fur)`} mask={`url(#${id}-mask)`}/>
    </svg>}
    <span key="finish" aria-hidden="true" className="glaze-layer glaze-finish" />
    <span key="highlight" aria-hidden="true" className="glaze-layer glaze-highlight" />
    <span key="bloom" aria-hidden="true" className="glaze-layer glaze-bloom" />
    {children}
  </Tag>;
}
