"use client";

// 之前是 Three.js 渲染的 3D 地球（带大气散射 shader），用户要求换成 NASA
// Artemis II 实拍的弯月地球静态背景，不动、无装饰。
// 保留组件名 Earth3D 是因为 match/page.tsx 还在 import 它，不必动调用方。

export default function Earth3D({ className = "" }: { className?: string }) {
  return (
    <div
      className={"absolute inset-0 pointer-events-none " + className}
      style={{
        backgroundImage: "url(/textures/match_bg.jpg)",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
        backgroundColor: "#000",
      }}
    />
  );
}
