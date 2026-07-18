"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useRef, Suspense, useEffect, useState } from "react";
import * as THREE from "three";
import { useTexture, Stars } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";

// ─── 星球数据 ──────────────────────────────────────────────────────────────
interface PlanetDef {
  name: string;
  texture: string;
  size: number;
  orbit: number;
  speed: number;
  phase: number;
  tilt?: number;
  atmosphere?: string;
}

const PLANETS: PlanetDef[] = [
  { name: "Mercury", texture: "/textures/mercury.jpg",  size: 0.045, orbit: 1.25, speed: 0.47, phase: 0.0 },
  { name: "Venus",   texture: "/textures/venus.jpg",    size: 0.075, orbit: 1.75, speed: 0.35, phase: 1.1, atmosphere: "#e8b47a" },
  { name: "Earth",   texture: "/textures/earth.jpg",    size: 0.082, orbit: 2.45, speed: 0.27, phase: 2.4, atmosphere: "#4fc3f7" },
  { name: "Mars",    texture: "/textures/mars.jpg",     size: 0.065, orbit: 3.05, speed: 0.21, phase: 3.7, atmosphere: "#e64a19" },
  { name: "Jupiter", texture: "/textures/jupiter.jpg",  size: 0.21,  orbit: 4.4,  speed: 0.12, phase: 0.6 },
  { name: "Saturn",  texture: "/textures/saturn.jpg",   size: 0.17,  orbit: 5.6,  speed: 0.09, phase: 2.0 },
  { name: "Uranus",  texture: "/textures/uranus.jpg",   size: 0.12,  orbit: 6.8,  speed: 0.06, phase: 4.8, tilt: 1.7 },
  { name: "Neptune", texture: "/textures/neptune.jpg",  size: 0.12,  orbit: 7.8,  speed: 0.045, phase: 1.5 },
];

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = (event: MediaQueryListEvent) => {
      setPrefersReducedMotion(event.matches);
    };

    setPrefersReducedMotion(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);

    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, []);

  return prefersReducedMotion;
}

function VisibilityController({
  onVisibilityChange,
  prefersReducedMotion,
}: {
  onVisibilityChange: (isVisible: boolean) => void;
  prefersReducedMotion: boolean;
}) {
  const get = useThree((state) => state.get);
  const pausedElapsed = useRef(0);
  const visibleFrameloop = prefersReducedMotion ? "demand" : "always";

  useEffect(() => {
    const handleVisibilityChange = () => {
      const state = get();
      const isPageVisible = !document.hidden;

      if (!isPageVisible && state.frameloop !== "never") {
        pausedElapsed.current = state.clock.getElapsedTime();
        state.setFrameloop("never");
      } else if (isPageVisible && state.frameloop !== visibleFrameloop) {
        const wasStopped = state.frameloop === "never";
        state.setFrameloop(visibleFrameloop);
        if (wasStopped) state.clock.elapsedTime = pausedElapsed.current;
        state.invalidate();
      }

      onVisibilityChange(isPageVisible);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    handleVisibilityChange();

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [get, onVisibilityChange, visibleFrameloop]);

  return null;
}

// ─── 银河背景球 ───────────────────────────────────────────────────────────
function CosmosBackground() {
  const texture = useTexture("/textures/milkyway.jpg");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    texture.colorSpace = THREE.SRGBColorSpace;
  }, [texture]);
  return (
    <mesh>
      <sphereGeometry args={[500, 64, 40]} />
      <meshBasicMaterial map={texture} side={THREE.BackSide} />
    </mesh>
  );
}

// ─── 太阳 ─────────────────────────────────────────────────────────────────
function SunMesh() {
  const texture = useTexture("/textures/sun.jpg");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    texture.colorSpace = THREE.SRGBColorSpace;
  }, [texture]);
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame(({ clock }) => {
    meshRef.current.rotation.y = clock.elapsedTime * 0.08;
  });

  return (
    <group>
      <pointLight intensity={4} distance={40} color="#ffe0a0" decay={1.5} />
      {/* 核心球 */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[0.52, 64, 64]} />
        <meshBasicMaterial map={texture} />
      </mesh>
    </group>
  );
}


// ─── 土星环 ───────────────────────────────────────────────────────────────
function SaturnRing() {
  const texture = useTexture("/textures/saturn_ring.png");
  return (
    <mesh rotation={[Math.PI / 2 - 0.45, 0, 0]}>
      <ringGeometry args={[0.26, 0.46, 128]} />
      <meshBasicMaterial
        map={texture}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

// ─── 单颗星球 ─────────────────────────────────────────────────────────────
function PlanetMesh({ planet }: { planet: PlanetDef }) {
  const texture = useTexture(planet.texture);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    texture.colorSpace = THREE.SRGBColorSpace;
  }, [texture]);
  const groupRef = useRef<THREE.Group>(null!);
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const a = (t * planet.speed + planet.phase) % (Math.PI * 2);
    groupRef.current.position.set(
      Math.cos(a) * planet.orbit,
      0,
      Math.sin(a) * planet.orbit,
    );
    if (planet.tilt) meshRef.current.rotation.z = planet.tilt;
    meshRef.current.rotation.y = t * 0.35;
  });

  return (
    <group ref={groupRef}>
      <mesh ref={meshRef}>
        <sphereGeometry args={[planet.size, 48, 48]} />
        <meshStandardMaterial
          map={texture}
          roughness={0.75}
          metalness={0.05}
        />
      </mesh>
      {/* 大气光晕 */}
      {planet.atmosphere && (
        <mesh>
          <sphereGeometry args={[planet.size * 1.14, 32, 32]} />
          <meshBasicMaterial
            color={planet.atmosphere}
            transparent opacity={0.12}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      )}
      {/* 土星环 */}
      {planet.name === "Saturn" && (
        <Suspense fallback={null}>
          <SaturnRing />
        </Suspense>
      )}
    </group>
  );
}

// ─── 完整场景 ─────────────────────────────────────────────────────────────
function Scene() {
  const sceneRef = useRef<THREE.Group>(null!);

  useFrame(({ clock }) => {
    // 整体缓慢自转，全息感
    sceneRef.current.rotation.y = clock.elapsedTime * 0.025;
  });

  return (
    <group ref={sceneRef}>
      <Suspense fallback={null}>
        <CosmosBackground />
        <SunMesh />
        {PLANETS.map((p) => (
          <Suspense key={p.name} fallback={null}>
            <PlanetMesh planet={p} />
          </Suspense>
        ))}
      </Suspense>
    </group>
  );
}

// ─── 导出 ─────────────────────────────────────────────────────────────────
export default function SolarSystem3D({ className = "" }: { className?: string }) {
  const [isPageVisible, setIsPageVisible] = useState(true);
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div className={"absolute inset-0 pointer-events-none " + className}>
      {/* 全息扫描线叠层 */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: "repeating-linear-gradient(180deg, transparent, transparent 3px, rgba(242,168,60,0.012) 3px, rgba(242,168,60,0.012) 4px)",
          mixBlendMode: "screen",
        }}
      />
      {/* 边缘暗角 */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at 50% 50%, transparent 45%, rgba(0,0,15,0.65) 100%)",
        }}
      />
      <Canvas
        camera={{ position: [0, 3.8, 11], fov: 44 }}
        gl={{ alpha: true, antialias: true, powerPreference: "high-performance", toneMapping: THREE.ACESFilmicToneMapping }}
        dpr={[1, 1.5]}
        frameloop={isPageVisible ? (prefersReducedMotion ? "demand" : "always") : "never"}
      >
        <VisibilityController
          onVisibilityChange={setIsPageVisible}
          prefersReducedMotion={prefersReducedMotion}
        />
        <ambientLight intensity={0.18} />
        <Scene />
        <Stars radius={300} depth={60} count={8000} factor={4} saturation={0.5} fade speed={0.6} />
        <EffectComposer>
          <Bloom
            intensity={1.4}
            luminanceThreshold={0.15}
            luminanceSmoothing={0.85}
            mipmapBlur
          />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
