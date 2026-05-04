import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';

type ModelViewerProps = {
  jobId?: string;
  stlUrl?: string;
};

export default function ModelViewer({ jobId, stlUrl }: ModelViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    const modelUrl = stlUrl || (jobId ? `/api/connector-cad/jobs/${jobId}/files/model.stl` : '');
    if (!modelUrl) {
      setFailed(true);
      return undefined;
    }

    setFailed(false);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xfafafa);

    const camera = new THREE.PerspectiveCamera(42, mount.clientWidth / mount.clientHeight, 0.1, 1000);
    camera.position.set(52, -58, 38);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.target.set(0, 0, 0);

    scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d8d8, 2.0));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.6);
    keyLight.position.set(35, -45, 60);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.8);
    fillLight.position.set(-40, 30, 30);
    scene.add(fillLight);

    const grid = new THREE.GridHelper(90, 18, 0xcfcfcf, 0xe8e8e8);
    grid.position.z = -7;
    scene.add(grid);

    const axes = new THREE.AxesHelper(20);
    axes.position.set(-32, -28, -6.9);
    scene.add(axes);

    const loader = new STLLoader();
    loader.load(
      modelUrl,
      (geometry) => {
        geometry.computeVertexNormals();
        geometry.center();

        const material = new THREE.MeshStandardMaterial({
          color: 0xf4f4f1,
          roughness: 0.74,
          metalness: 0.03,
        });
        const mesh = new THREE.Mesh(geometry, material);
        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3());
        const maxAxis = Math.max(size.x, size.y, size.z) || 1;
        mesh.scale.setScalar(42 / maxAxis);
        mesh.rotation.x = -Math.PI / 2;
        scene.add(mesh);
      },
      undefined,
      () => setFailed(true),
    );

    const resize = () => {
      if (!mount.clientWidth || !mount.clientHeight) return;
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    };
    window.addEventListener('resize', resize);

    let frame = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      controls.dispose();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        const material = mesh.material;
        if (Array.isArray(material)) material.forEach((item) => item.dispose());
        else if (material) material.dispose();
      });
      renderer.dispose();
      mount.replaceChildren();
    };
  }, [jobId, stlUrl]);

  return (
    <div className="model-viewer">
      <div ref={mountRef} className="model-viewer-canvas" />
      {failed && <div className="model-viewer-error">模型预览失败，但 STEP/DXF 仍可下载</div>}
    </div>
  );
}
