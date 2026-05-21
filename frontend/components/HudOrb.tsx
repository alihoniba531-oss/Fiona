"use client";

import dynamic from "next/dynamic";

interface Props {
  recording?: boolean;
  size?: number;
}

const HudOrb3D = dynamic(() => import("./HudOrb3D"), {
  ssr: false,
  loading: () => null,
});

export default function HudOrb(props: Props) {
  return <HudOrb3D {...props} />;
}
