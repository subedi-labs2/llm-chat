import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import {
  MathUtils,
  type Group,
  type Mesh,
  type MeshStandardMaterial,
} from "three";

const TEAL = "#2dd4bf";
const SHELL = "#e2e8f0";
const ACCENT = "#0f766e";

type Pointer = { x: number; y: number } | null;

type RobotHeadProps = {
  entering: boolean;
  reducedMotion: boolean;
};

// Tracks the pointer across the whole window (not just the canvas) so the
// head keeps following while the cursor is over text, buttons, or the chat.
function useWindowPointer() {
  const pointer = useRef<Pointer>(null);

  useEffect(() => {
    function onMove(event: PointerEvent) {
      pointer.current = { x: event.clientX, y: event.clientY };
    }
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  return pointer;
}

function Head({
  entering,
  reducedMotion,
  pointer,
}: RobotHeadProps & { pointer: React.RefObject<Pointer> }) {
  const root = useRef<Group>(null);
  const eyes = useRef<Group>(null);
  const leftEye = useRef<Mesh>(null);
  const rightEye = useRef<Mesh>(null);
  const mouth = useRef<Mesh>(null);
  const antennaTip = useRef<MeshStandardMaterial>(null);
  const nextBlink = useRef(2);
  const enterStart = useRef<number | null>(null);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const head = root.current;
    if (!head) return;

    // Aim relative to where the head is on screen, so it still looks at the
    // cursor once it has shrunk into the site header.
    let x = 0;
    let y = 0;
    if (pointer.current) {
      const rect = state.gl.domElement.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      x = MathUtils.clamp(
        (pointer.current.x - cx) / (window.innerWidth / 2),
        -1,
        1,
      );
      y = MathUtils.clamp(
        (cy - pointer.current.y) / (window.innerHeight / 2),
        -1,
        1,
      );
    }
    let targetY = x * 0.7;
    let targetX = -y * 0.45;

    // Nod toward the viewer when entering.
    if (entering) {
      enterStart.current ??= t;
      const p = Math.min((t - enterStart.current) / 0.5, 1);
      targetY = 0;
      targetX = Math.sin(p * Math.PI) * 0.45;
    } else {
      enterStart.current = null;
    }

    const lambda = reducedMotion ? 20 : 6;
    head.rotation.y = MathUtils.damp(head.rotation.y, targetY, lambda, delta);
    head.rotation.x = MathUtils.damp(head.rotation.x, targetX, lambda, delta);
    head.rotation.z = MathUtils.damp(head.rotation.z, -x * 0.08, 4, delta);
    head.position.y = reducedMotion ? 0 : Math.sin(t * 1.4) * 0.06;

    if (eyes.current) {
      eyes.current.position.x = MathUtils.damp(
        eyes.current.position.x,
        x * 0.06,
        8,
        delta,
      );
      eyes.current.position.y = MathUtils.damp(
        eyes.current.position.y,
        y * 0.04,
        8,
        delta,
      );
    }

    // Blink periodically; squint happily while entering.
    let eyeScale = 1;
    if (entering) {
      eyeScale = 0.35;
    } else if (!reducedMotion) {
      if (t > nextBlink.current + 0.14) {
        nextBlink.current = t + 2 + Math.random() * 3;
      } else if (t > nextBlink.current) {
        eyeScale = 0.1;
      }
    }
    for (const eye of [leftEye.current, rightEye.current]) {
      if (eye) eye.scale.y = MathUtils.damp(eye.scale.y, eyeScale, 30, delta);
    }

    if (mouth.current) {
      const smile = entering ? 1.4 : 1;
      mouth.current.scale.x = MathUtils.damp(
        mouth.current.scale.x,
        smile,
        10,
        delta,
      );
    }

    if (antennaTip.current) {
      antennaTip.current.emissiveIntensity = reducedMotion
        ? 2
        : 1.5 + Math.sin(t * 3);
    }
  });

  return (
    <group ref={root}>
      <group scale={[1.1, 1, 1]}>
        <mesh>
          <sphereGeometry args={[1, 64, 64]} />
          <meshStandardMaterial
            color={SHELL}
            roughness={0.35}
            metalness={0.15}
          />
        </mesh>

        {/* Visor: a front-facing slice of a slightly larger sphere. */}
        <mesh>
          <sphereGeometry
            args={[
              1.02,
              64,
              32,
              Math.PI / 2 - 0.95,
              1.9,
              Math.PI / 2 - 0.5,
              0.95,
            ]}
          />
          <meshStandardMaterial
            color="#0b1220"
            roughness={0.12}
            metalness={0.6}
          />
        </mesh>

        <mesh rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[1.0, 0.07, 16, 64, Math.PI * 0.72]} />
          <meshStandardMaterial color={ACCENT} roughness={0.4} />
        </mesh>

        <group ref={eyes}>
          <mesh
            ref={leftEye}
            position={[-0.32, 0.06, 0.99]}
            rotation={[0, -0.3, 0]}
          >
            <capsuleGeometry args={[0.09, 0.14, 8, 16]} />
            <meshStandardMaterial
              color={TEAL}
              emissive={TEAL}
              emissiveIntensity={2.5}
              toneMapped={false}
            />
          </mesh>
          <mesh
            ref={rightEye}
            position={[0.32, 0.06, 0.99]}
            rotation={[0, 0.3, 0]}
          >
            <capsuleGeometry args={[0.09, 0.14, 8, 16]} />
            <meshStandardMaterial
              color={TEAL}
              emissive={TEAL}
              emissiveIntensity={2.5}
              toneMapped={false}
            />
          </mesh>
        </group>

        <mesh
          ref={mouth}
          position={[0, -0.22, 0.975]}
          rotation={[0, 0, Math.PI + 0.6]}
        >
          <torusGeometry args={[0.14, 0.022, 8, 32, Math.PI - 1.2]} />
          <meshStandardMaterial
            color={TEAL}
            emissive={TEAL}
            emissiveIntensity={1.6}
            toneMapped={false}
          />
        </mesh>
      </group>

      {[-1, 1].map((side) => (
        <group
          key={side}
          position={[side * 1.1, 0, 0]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <mesh>
            <cylinderGeometry args={[0.26, 0.26, 0.16, 32]} />
            <meshStandardMaterial color={ACCENT} roughness={0.4} />
          </mesh>
          <mesh position={[0, side * -0.09, 0]}>
            <cylinderGeometry args={[0.14, 0.14, 0.04, 32]} />
            <meshStandardMaterial
              color={TEAL}
              emissive={TEAL}
              emissiveIntensity={0.8}
            />
          </mesh>
        </group>
      ))}

      <mesh position={[0, 1.15, 0]}>
        <cylinderGeometry args={[0.025, 0.035, 0.35, 12]} />
        <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.3} />
      </mesh>
      <mesh position={[0, 1.36, 0]}>
        <sphereGeometry args={[0.08, 24, 24]} />
        <meshStandardMaterial
          ref={antennaTip}
          color={TEAL}
          emissive={TEAL}
          emissiveIntensity={2}
          toneMapped={false}
        />
      </mesh>

      <mesh position={[0, -1.05, 0]}>
        <cylinderGeometry args={[0.38, 0.5, 0.3, 32]} />
        <meshStandardMaterial color="#64748b" metalness={0.4} roughness={0.4} />
      </mesh>
    </group>
  );
}

export default function RobotHead({ entering, reducedMotion }: RobotHeadProps) {
  const pointer = useWindowPointer();

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 0, 5.2], fov: 35 }}
      gl={{ antialias: true, alpha: true }}
      fallback={null}
      aria-hidden="true"
    >
      <ambientLight intensity={0.55} />
      <hemisphereLight args={["#e0f2fe", "#0f172a", 0.6]} />
      <directionalLight position={[3, 4, 5]} intensity={2.2} />
      <pointLight position={[-3, -1, 2]} intensity={8} color={TEAL} />
      <pointLight position={[0, 2, -3]} intensity={10} color="#38bdf8" />
      <Head
        entering={entering}
        reducedMotion={reducedMotion}
        pointer={pointer}
      />
    </Canvas>
  );
}
