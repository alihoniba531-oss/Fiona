"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import { createNoise3D } from "simplex-noise";
import * as THREE from "three";
import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

interface Props {
  recording?: boolean;
  size?: number;
}

const PARTICLE_COUNT = 900;
const COLOR_IDLE = new THREE.Color("#f2a83c");
const COLOR_REC = new THREE.Color("#ff5a4d");

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

function fibonacciSphere(count: number) {
  const arr = new Float32Array(count * 3);
  const phi = Math.PI * (Math.sqrt(5) - 1);
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    arr[i * 3] = Math.cos(theta) * r;
    arr[i * 3 + 1] = y;
    arr[i * 3 + 2] = Math.sin(theta) * r;
  }
  return arr;
}

function ParticleField({
  recording,
  prefersReducedMotion,
}: {
  recording: boolean;
  prefersReducedMotion: boolean;
}) {
  const pointsRef = useRef<THREE.Points>(null!);
  const matRef = useRef<THREE.PointsMaterial>(null!);
  const invalidate = useThree((state) => state.invalidate);

  // 两套独立的 3D noise — 一套做大块隆起，一套做表面触手细节
  const noiseLow = useMemo(() => createNoise3D(), []);
  const noiseHigh = useMemo(() => createNoise3D(), []);

  // 平滑状态过渡
  const ampLowRef = useRef(0.18);
  const ampHighRef = useRef(0.06);
  const speedRef = useRef(0.28);

  const { positions, basePositions } = useMemo(() => {
    const basePositions = fibonacciSphere(PARTICLE_COUNT);
    const positions = new Float32Array(basePositions);
    return { positions, basePositions };
  }, []);

  useEffect(() => {
    if (!prefersReducedMotion) return;
    matRef.current.color.copy(recording ? COLOR_REC : COLOR_IDLE);
    matRef.current.size = recording ? 0.036 : 0.026;
    invalidate();
  }, [invalidate, prefersReducedMotion, recording]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;

    // 待机：温润缓慢的不对称起伏
    // 录音：剧烈、像有东西要从里面冲出来
    const targetAmpLow = recording ? 0.55 : 0.22;
    const targetAmpHigh = recording ? 0.22 : 0.07;
    const targetSpeed = recording ? 0.95 : 0.32;
    ampLowRef.current += (targetAmpLow - ampLowRef.current) * 0.06;
    ampHighRef.current += (targetAmpHigh - ampHighRef.current) * 0.06;
    speedRef.current += (targetSpeed - speedRef.current) * 0.06;

    const ampLow = ampLowRef.current;
    const ampHigh = ampHighRef.current;
    const speed = speedRef.current;

    const freqLow = 1.3;
    const freqHigh = 3.6;
    const tLow = t * speed;
    const tHigh = t * speed * 1.7;

    const pos = pointsRef.current.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;
      const bx = basePositions[i3];
      const by = basePositions[i3 + 1];
      const bz = basePositions[i3 + 2];

      // 用 4D-ish noise：把时间塞进一个坐标里，整团噪声场会"流动"
      const n1 = noiseLow(bx * freqLow + tLow, by * freqLow, bz * freqLow - tLow * 0.6);
      const n2 = noiseHigh(bx * freqHigh, by * freqHigh + tHigh, bz * freqHigh);

      // 半正态化：让 noise 更多往外凸，少向内陷（毒液质感更像挤出的触手）
      const disp = 1 + Math.max(n1, n1 * 0.4) * ampLow + n2 * ampHigh;

      pos[i3] = bx * disp;
      pos[i3 + 1] = by * disp;
      pos[i3 + 2] = bz * disp;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;

    // 慢转，配合噪声流动，整体像"活物"
    pointsRef.current.rotation.y = t * 0.08;
    pointsRef.current.rotation.x = Math.sin(t * 0.05) * 0.18;

    matRef.current.color.lerp(recording ? COLOR_REC : COLOR_IDLE, 0.06);
    const targetSize = recording ? 0.036 : 0.026;
    matRef.current.size += (targetSize - matRef.current.size) * 0.08;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={PARTICLE_COUNT}
        />
      </bufferGeometry>
      <pointsMaterial
        ref={matRef}
        size={0.026}
        sizeAttenuation
        transparent
        opacity={0.95}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function CoreGlow({
  recording,
  prefersReducedMotion,
}: {
  recording: boolean;
  prefersReducedMotion: boolean;
}) {
  const ref = useRef<THREE.Mesh>(null!);
  const matRef = useRef<THREE.MeshBasicMaterial>(null!);
  const invalidate = useThree((state) => state.invalidate);
  const noise = useMemo(() => createNoise3D(), []);

  useEffect(() => {
    if (!prefersReducedMotion) return;
    matRef.current.color.copy(recording ? COLOR_REC : COLOR_IDLE);
    matRef.current.opacity = recording ? 0.32 : 0.2;
    invalidate();
  }, [invalidate, prefersReducedMotion, recording]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    // 核心也用 noise 做不规则形变（缩放三轴不一致）
    const speed = recording ? 1.4 : 0.5;
    const amp = recording ? 0.18 : 0.07;
    const base = recording ? 0.4 : 0.32;
    ref.current.scale.x = base + noise(t * speed, 0, 0) * amp;
    ref.current.scale.y = base + noise(0, t * speed, 7.3) * amp;
    ref.current.scale.z = base + noise(11.1, 0, t * speed) * amp;
    matRef.current.color.lerp(recording ? COLOR_REC : COLOR_IDLE, 0.06);
    matRef.current.opacity = recording ? 0.32 : 0.2;
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1, 24, 24]} />
      <meshBasicMaterial
        ref={matRef}
        transparent
        opacity={0.2}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
}

export default function HudOrb3D({ recording = false, size = 240 }: Props) {
  const [isPageVisible, setIsPageVisible] = useState(true);
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div style={{ width: size, height: size }} className="select-none">
      <Canvas
        camera={{ position: [0, 0, 3.2], fov: 45 }}
        gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
        dpr={[1, 1.5]}
        frameloop={isPageVisible ? (prefersReducedMotion ? "demand" : "always") : "never"}
      >
        <VisibilityController
          onVisibilityChange={setIsPageVisible}
          prefersReducedMotion={prefersReducedMotion}
        />
        <ParticleField recording={recording} prefersReducedMotion={prefersReducedMotion} />
        <CoreGlow recording={recording} prefersReducedMotion={prefersReducedMotion} />
      </Canvas>
    </div>
  );
}
