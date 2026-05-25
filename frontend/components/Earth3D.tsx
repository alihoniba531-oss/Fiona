"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useRef, Suspense, useMemo } from "react";
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

// ─── 地球本体 ───
// Blue Marble 日图 + 城市灯夜图 (emissive) + 法线 bump。
// metalness 中度 + 低 roughness：海洋有镜面反光（真实地球在太空标志特征）。
function EarthMesh() {
  const [dayMap, nightMap, normalMap] = useTexture([
    "/textures/earth_day_2k.jpg",
    "/textures/earth_night_2k.jpg",
    "/textures/earth_normal.jpg",
  ]);
  dayMap.colorSpace = THREE.SRGBColorSpace;
  nightMap.colorSpace = THREE.SRGBColorSpace;
  dayMap.anisotropy = 16;
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame(({ clock }) => {
    meshRef.current.rotation.y = clock.elapsedTime * 0.04;
  });

  // 地轴 23.4° 倾角
  return (
    <group rotation={[0, 0, 0.408]}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1, 256, 256]} />
        <meshStandardMaterial
          map={dayMap}
          normalMap={normalMap}
          normalScale={new THREE.Vector2(0.85, 0.85)}
          // 夜面 emissive = 城市灯 (太阳照不到时唯一可见的)
          emissiveMap={nightMap}
          emissive={new THREE.Color("#ffdc8a")}
          emissiveIntensity={1.2}
          // 海洋光泽：metalness 适中让海面反光（陆地法线粗糙度也压住反射）
          roughness={0.55}
          metalness={0.35}
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
    meshRef.current.rotation.y = clock.elapsedTime * 0.052;
  });

  return (
    <group rotation={[0, 0, 0.408]}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1.012, 128, 128]} />
        <meshStandardMaterial
          map={cloudsMap}
          alphaMap={cloudsMap}
          transparent
          opacity={0.9}
          depthWrite={false}
          roughness={1}
          metalness={0}
        />
      </mesh>
    </group>
  );
}

// ─── 大气层光晕（菲涅耳 shader）───
// 地球从太空看的标志特征：边缘一圈蓝色光晕。
// 做法：套一个略大的球（背面渲染），shader 算 1 - dot(normal, view)，
// 边缘（normal 垂直于 view）出现强光，正中心透明。
function AtmosphereHalo() {
  const material = useMemo(() => new THREE.ShaderMaterial({
    side: THREE.BackSide,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    uniforms: {
      uColor: { value: new THREE.Color("#5cb6ff") },
      uIntensity: { value: 1.6 },
      uPower: { value: 3.0 },
    },
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vNormal = normalize(normalMatrix * normal);
        vViewDir = normalize(-mvPosition.xyz);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      varying vec3 vViewDir;
      uniform vec3 uColor;
      uniform float uIntensity;
      uniform float uPower;
      void main() {
        float rim = 1.0 - abs(dot(vNormal, vViewDir));
        float halo = pow(rim, uPower) * uIntensity;
        gl_FragColor = vec4(uColor * halo, halo);
      }
    `,
  }), []);

  return (
    <mesh>
      <sphereGeometry args={[1.05, 64, 64]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

function Scene() {
  return (
    <Suspense fallback={null}>
      <CosmosBackground />
      <EarthMesh />
      <CloudsMesh />
      <AtmosphereHalo />
    </Suspense>
  );
}

export default function Earth3D({ className = "" }: { className?: string }) {
  return (
    <div className={"absolute inset-0 pointer-events-none " + className}>
      <Canvas
        camera={{ position: [0, 0, 6.5], fov: 38 }}
        gl={{
          alpha: true,
          antialias: true,
          powerPreference: "high-performance",
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.0,
        }}
        dpr={[1, 2]}
      >
        {/*
          光照配方（真实太空视角）：
          - directional：太阳光，从一侧斜射，制造明显的晨昏线 / 半边夜
          - ambient：极弱兜底防止背面纯黑（实际太空里背面就是该极暗）
          - 不用 hemisphereLight：之前给海洋叠了过强蓝调，反而像塑料
        */}
        <ambientLight intensity={0.05} />
        <directionalLight
          position={[5, 1.5, 3]}
          intensity={3.8}
          color="#fffaf0"
        />
        <Scene />
        <Stars radius={300} depth={60} count={6000} factor={3} saturation={0} fade speed={0.4} />
      </Canvas>
    </div>
  );
}
