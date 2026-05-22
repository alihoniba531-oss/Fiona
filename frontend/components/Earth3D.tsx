"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useRef, Suspense } from "react";
import * as THREE from "three";
import { useTexture, Stars } from "@react-three/drei";

// ─── 银河背景球 ───
function CosmosBackground() {
  const texture = useTexture("/textures/milkyway.jpg");
  texture.colorSpace = THREE.SRGBColorSpace;
  return (
    <mesh>
      <sphereGeometry args={[500, 64, 40]} />
      <meshBasicMaterial map={texture} side={THREE.BackSide} />
    </mesh>
  );
}

// ─── 地球 (Blue Marble 日图 + 城市灯夜图 + 法线 bump) ───
function EarthMesh() {
  const [dayMap, nightMap, normalMap] = useTexture([
    "/textures/earth_day_2k.jpg",
    "/textures/earth_night_2k.jpg",
    "/textures/earth_normal.jpg",
  ]);
  dayMap.colorSpace = THREE.SRGBColorSpace;
  nightMap.colorSpace = THREE.SRGBColorSpace;
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame(({ clock }) => {
    meshRef.current.rotation.y = clock.elapsedTime * 0.04;
  });

  // 地轴 23.4° 倾角
  return (
    <group rotation={[0, 0, 0.408]}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1, 128, 128]} />
        <meshStandardMaterial
          map={dayMap}
          normalMap={normalMap}
          normalScale={new THREE.Vector2(0.5, 0.5)}
          /* 夜面 emissive = 城市灯 + 海洋微辉 (太阳照不到时唯一可见的) */
          emissiveMap={nightMap}
          emissive={new THREE.Color("#ffe4a0")}
          emissiveIntensity={1.0}
          roughness={0.9}
          metalness={0.0}
        />
      </mesh>
    </group>
  );
}

// ─── 云层 (独立稍快旋转，半透明) ───
function CloudsMesh() {
  const cloudsMap = useTexture("/textures/earth_clouds_2k.jpg");
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame(({ clock }) => {
    meshRef.current.rotation.y = clock.elapsedTime * 0.055;
  });

  return (
    <group rotation={[0, 0, 0.408]}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1.012, 96, 96]} />
        <meshLambertMaterial
          map={cloudsMap}
          alphaMap={cloudsMap}
          transparent
          opacity={0.85}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function Scene() {
  return (
    <Suspense fallback={null}>
      <CosmosBackground />
      <EarthMesh />
      <CloudsMesh />
    </Suspense>
  );
}

export default function Earth3D({ className = "" }: { className?: string }) {
  return (
    <div className={"absolute inset-0 pointer-events-none " + className}>
      {/* 全息扫描线 */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background:
            "repeating-linear-gradient(180deg, transparent, transparent 3px, rgba(0,212,255,0.018) 3px, rgba(0,212,255,0.018) 4px)",
          mixBlendMode: "screen",
        }}
      />
      {/* 边缘暗角 */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 50%, transparent 45%, rgba(0,0,15,0.65) 100%)",
        }}
      />
      <Canvas
        camera={{ position: [0, 0, 6.5], fov: 38 }}
        gl={{
          alpha: true,
          antialias: true,
          powerPreference: "high-performance",
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.15,
        }}
        dpr={[1, 2]}
      >
        {/*
          光照配方：
          - 太阳：直射光从相机正后方，照亮昼半球
          - hemisphereLight：模拟大气散射，海洋反射蓝调
          - ambient：保留极弱兜底
        */}
        <ambientLight intensity={0.12} />
        <hemisphereLight args={["#88baff", "#0a1428", 0.55]} />
        <directionalLight position={[0.3, 0.4, 8]} intensity={3.2} color="#fffaf0" />
        <Scene />
        <Stars radius={300} depth={60} count={6000} factor={3} saturation={0} fade speed={0.4} />
      </Canvas>
    </div>
  );
}
