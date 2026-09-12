import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Meta, Run, TrajectoryChunk } from "./types";

export const COLORS = ["#64e9b8", "#59c7ef", "#b99bff", "#f3a564"];
const RGB = COLORS.map(c => new THREE.Color(c));

export class Chamber {
  readonly renderer: THREE.WebGLRenderer;
  readonly camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
  readonly scene = new THREE.Scene();
  readonly controls: OrbitControls;
  private chamber = new THREE.Group();
  private paths = new THREE.Group();
  private chunks: TrajectoryChunk[] = [];
  private run?: Run;
  private meta?: Meta;
  private lineMaterial?: THREE.ShaderMaterial;
  private heads?: THREE.Points;
  private sphere?: THREE.Mesh;
  private channels = [true, true, true, true];
  private dirty = true;
  private timeUs = 0;
  segments = 0;
  rendererName = "WebGL2";
  onStats: () => void = () => undefined;

  constructor(private host: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x0c131c, 0);
    this.host.append(this.renderer.domElement);
    this.renderer.domElement.setAttribute("aria-label", "Interactive 3D electron trajectories. Drag to orbit, scroll to zoom.");
    this.renderer.domElement.setAttribute("role", "img");
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = 15;
    this.controls.addEventListener("change", () => { this.dirty = true; });
    this.scene.add(this.chamber, this.paths);
    this.scene.add(new THREE.AmbientLight(0xffffff, 2));
    const light = new THREE.DirectionalLight(0xbbddff, 3);
    light.position.set(3, -2, 5); this.scene.add(light);
    const gl = this.renderer.getContext();
    const debug = gl.getExtension("WEBGL_debug_renderer_info");
    if (debug) this.rendererName = String(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL));
    new ResizeObserver(() => this.resize()).observe(host);
    this.resetView("iso"); this.resize();
    this.renderer.setAnimationLoop(() => {
      this.controls.update();
      if (this.dirty) { this.renderer.render(this.scene, this.camera); this.dirty = false; }
    });
  }

  private resize(): void {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); this.dirty = true;
  }

  private clear(group: THREE.Group): void {
    group.traverse(object => {
      if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
        object.geometry.dispose();
        if (Array.isArray(object.material)) object.material.forEach(m => m.dispose());
        else object.material.dispose();
      }
    });
    group.clear();
  }

  setRun(run: Run, meta?: Meta): void {
    this.run = run; this.meta = meta; this.chunks = [];
    this.clear(this.chamber); this.clear(this.paths);
    this.heads = undefined; this.lineMaterial = undefined; this.sphere = undefined;
    this.segments = 0;
    const half = (meta?.summary.ring_half_sep_m ?? run.radiusM * 0.5) / run.radiusM;
    for (const [z, color] of [[-half, 0x5cc8dd], [half, 0xc6a571]]) {
      const coil = new THREE.Mesh(
        new THREE.TorusGeometry(1, 0.012, 8, 144),
        new THREE.MeshStandardMaterial({ color, metalness: 0.6, roughness: 0.3 }),
      );
      coil.position.z = z; this.chamber.add(coil);
      const halo = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(Array.from({ length: 144 }, (_, i) =>
          new THREE.Vector3(1.025 * Math.cos(i / 144 * Math.PI * 2), 1.025 * Math.sin(i / 144 * Math.PI * 2), z))),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.14 }),
      );
      this.chamber.add(halo);
    }
    const grid = new THREE.GridHelper(3.4, 20, 0x283e4e, 0x162835);
    grid.rotation.x = Math.PI / 2; grid.position.z = -Math.max(1.3, half + 0.8);
    this.chamber.add(grid);
    const axis = new THREE.AxesHelper(0.28);
    axis.position.set(-1.25, -1.25, grid.position.z + 0.01); this.chamber.add(axis);
    if (run.poisson) {
      const lower = new THREE.Vector3(...run.poisson.boxLowerM).divideScalar(run.radiusM);
      const upper = new THREE.Vector3(...run.poisson.boxUpperM).divideScalar(run.radiusM);
      this.chamber.add(new THREE.Box3Helper(new THREE.Box3(lower, upper), 0x526577));
    }
    if (meta && run.chargeC !== 0) {
      this.sphere = new THREE.Mesh(
        new THREE.SphereGeometry((meta.summary.space_charge_radius_m ?? run.radiusM * 0.3) / run.radiusM, 32, 24),
        new THREE.MeshBasicMaterial({ color: run.chargeC < 0 ? 0x769be6 : 0xe8b570, transparent: true,
          opacity: 0.08, depthWrite: false, wireframe: true }),
      );
      this.chamber.add(this.sphere);
    }
    const origin = meta?.summary.gun_position_m;
    const aim = meta?.summary.gun_direction_unit;
    if (origin && aim) {
      const point = new THREE.Vector3(...origin).divideScalar(run.radiusM);
      const gun = new THREE.Mesh(new THREE.SphereGeometry(0.025, 12, 8), new THREE.MeshBasicMaterial({ color: 0xf0f9ff }));
      gun.position.copy(point); this.chamber.add(gun);
      this.chamber.add(new THREE.ArrowHelper(new THREE.Vector3(...aim).normalize(), point, 0.23, 0xd6ebf3, 0.055, 0.025));
    }
    this.timeUs = run.trajectoryWindowUs;
    this.dirty = true; this.onStats();
  }

  setChunks(chunks: TrajectoryChunk[]): void { this.chunks = chunks; this.rebuild(); }
  setChannels(channels: boolean[]): void { this.channels = channels; this.rebuild(); }
  showSphere(show: boolean): void { if (this.sphere) this.sphere.visible = show; this.dirty = true; }

  private rebuild(): void {
    this.clear(this.paths); this.heads = undefined;
    if (!this.run || !this.meta) return;
    const positions: number[] = [], colors: number[] = [], times: number[] = [];
    const scale = this.run.radiusM;
    const sampleUs = this.meta.trajectory.sampleNs * 0.001;
    for (const chunk of this.chunks) {
      for (let p = 0; p < chunk.count; p++) {
        const code = this.meta.trajectory.exits[chunk.first + p];
        if (!this.channels[code]) continue;
        for (let f = 1; f < chunk.frames; f++) {
          const a = (p * chunk.frames + f - 1) * 3, b = a + 3;
          if (![...chunk.positions.subarray(a, a + 3), ...chunk.positions.subarray(b, b + 3)].every(Number.isFinite)) continue;
          for (const offset of [a, b]) {
            positions.push(chunk.positions[offset] / scale, chunk.positions[offset + 1] / scale, chunk.positions[offset + 2] / scale);
            colors.push(RGB[code].r, RGB[code].g, RGB[code].b);
          }
          times.push(chunk.indices[f - 1] * sampleUs, chunk.indices[f] * sampleUs);
        }
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("aColor", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setAttribute("aTime", new THREE.Float32BufferAttribute(times, 1));
    this.lineMaterial = new THREE.ShaderMaterial({
      uniforms: { uTime: { value: this.timeUs } }, transparent: true, depthWrite: false,
      vertexShader: `attribute vec3 aColor; attribute float aTime; varying vec3 vColor; varying float vTime;
        void main(){vColor=aColor;vTime=aTime;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
      fragmentShader: `uniform float uTime; varying vec3 vColor; varying float vTime;
        void main(){if(vTime>uTime)discard;gl_FragColor=vec4(vColor,.65);}`,
    });
    this.paths.add(new THREE.LineSegments(geometry, this.lineMaterial));
    const n = this.chunks.reduce((sum, c) => sum + c.count, 0);
    const heads = new THREE.BufferGeometry();
    heads.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(n * 3), 3));
    heads.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(n * 3), 3));
    this.heads = new THREE.Points(heads, new THREE.PointsMaterial({
      size: 5, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.9,
    }));
    this.heads.frustumCulled = false;
    this.paths.add(this.heads);
    this.segments = positions.length / 6;
    this.setTime(this.timeUs); this.onStats();
  }

  setTime(timeUs: number): void {
    this.timeUs = timeUs;
    if (this.lineMaterial) this.lineMaterial.uniforms.uTime.value = timeUs;
    if (this.heads && this.run && this.meta) {
      const attr = this.heads.geometry.getAttribute("position");
      const color = this.heads.geometry.getAttribute("color");
      let head = 0;
      const target = timeUs / (this.meta.trajectory.sampleNs * 0.001);
      for (const chunk of this.chunks) {
        let low = 0, high = chunk.frames - 1;
        while (low < high) {
          const mid = Math.ceil((low + high) / 2);
          if (chunk.indices[mid] <= target) low = mid; else high = mid - 1;
        }
        for (let p = 0; p < chunk.count; p++, head++) {
          const code = this.meta.trajectory.exits[chunk.first + p];
          const offset = (p * chunk.frames + low) * 3;
          const escapeUs = this.meta.trajectory.escapeUs[chunk.first + p];
          const valid = this.channels[code] && Number.isFinite(chunk.positions[offset]) &&
            (escapeUs === null || timeUs < escapeUs);
          attr.setXYZ(head, valid ? chunk.positions[offset] / this.run.radiusM : 9999,
            valid ? chunk.positions[offset + 1] / this.run.radiusM : 9999,
            valid ? chunk.positions[offset + 2] / this.run.radiusM : 9999);
          color.setXYZ(head, RGB[code].r, RGB[code].g, RGB[code].b);
        }
      }
      attr.needsUpdate = true; color.needsUpdate = true;
    }
    this.dirty = true;
  }

  resetView(view: string): void {
    this.camera.position.set(...(view === "top" ? [0.001, 0, 4.8] :
      view === "side" ? [3.9, 0, 0.1] : [2.4, -3.2, 2.1]) as [number, number, number]);
    this.controls.target.set(0, 0, -0.05); this.controls.update(); this.dirty = true;
  }
}
