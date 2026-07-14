import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

const ThreatGlobe2 = ({ geoData }) => {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const globeRef = useRef(null);
  const markersRef = useRef([]);
  const cameraRef = useRef(null);

  // Mouse tracking for interactive rotation
  const targetRotation = useRef({ x: 0, y: 0 });
  const isMouseDown = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(
      75,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      1000
    );
    camera.position.z = 2.5;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.setClearColor(0x000000, 0);
    renderer.shadowMap.enabled = true;
    rendererRef.current = renderer;
    containerRef.current.appendChild(renderer.domElement);

    const geometry = new THREE.SphereGeometry(1, 96, 96);

    const canvas = document.createElement('canvas');
    canvas.width = 2048;
    canvas.height = 1024;
    const ctx = canvas.getContext('2d');

    // Simple textured look
    ctx.fillStyle = '#071126';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'rgba(3,169,244,0.08)';
    for (let i = 0; i < 600; i++) {
      const x = Math.random() * canvas.width;
      const y = Math.random() * canvas.height;
      ctx.fillRect(x, y, 20, 12);
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;

    const material = new THREE.MeshStandardMaterial({
      map: texture,
      emissive: 0x00111a,
      roughness: 0.6,
      metalness: 0.0,
    });

    const globe = new THREE.Mesh(geometry, material);
    scene.add(globe);
    globeRef.current = globe;

    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0x88f0ff, 0.8);
    dir.position.set(5, 3, 5);
    scene.add(dir);

    // stars
    const starsGeo = new THREE.BufferGeometry();
    const starsMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.02, opacity: 0.6, transparent: true });
    const starVerts = [];
    for (let i = 0; i < 400; i++) starVerts.push((Math.random() - 0.5) * 200, (Math.random() - 0.5) * 200, (Math.random() - 0.5) * 200);
    starsGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(starVerts), 3));
    const stars = new THREE.Points(starsGeo, starsMat);
    scene.add(stars);

    const addMarkers = (data) => {
      // remove old
      markersRef.current.forEach(m => scene.remove(m));
      markersRef.current = [];

      data.forEach((loc, idx) => {
        const lat = (loc.latitude * Math.PI) / 180;
        const lon = (loc.longitude * Math.PI) / 180;
        const x = Math.cos(lat) * Math.cos(lon);
        const y = Math.sin(lat);
        const z = Math.cos(lat) * Math.sin(lon);

        const group = new THREE.Group();

        const s = Math.min(0.08 + (loc.count || 1) * 0.02, 0.18);
        const sphere = new THREE.Mesh(new THREE.SphereGeometry(s, 12, 12), new THREE.MeshStandardMaterial({ color: 0xff4d4d, emissive: 0xff6b6b }));
        sphere.position.set(x, y, z);
        group.add(sphere);

        const ring = new THREE.Mesh(new THREE.TorusGeometry(s + 0.08, 0.01, 8, 32), new THREE.MeshBasicMaterial({ color: 0xff6666, transparent: true, opacity: 0.7 }));
        ring.position.set(x, y, z);
        // align ring to surface normal
        const vFrom = new THREE.Vector3(0, 0, 1);
        const vTo = new THREE.Vector3(x, y, z).normalize();
        ring.quaternion.setFromUnitVectors(vFrom, vTo);
        group.add(ring);

        group.userData = { loc };
        scene.add(group);
        markersRef.current.push(group);
      });
    };

    addMarkers(geoData || []);

    const onResize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    // interaction
    const onDown = () => (isMouseDown.current = true);
    const onUp = () => (isMouseDown.current = false);
    let lastX = 0, lastY = 0;
    const onMove = (e) => {
      if (!isMouseDown.current) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const dx = (e.clientX - rect.left - rect.width / 2) / rect.width;
      const dy = (e.clientY - rect.top - rect.height / 2) / rect.height;
      targetRotation.current.y += dx * 0.5;
      targetRotation.current.x += dy * 0.5;
    };
    renderer.domElement.addEventListener('mousedown', onDown);
    renderer.domElement.addEventListener('mouseup', onUp);
    renderer.domElement.addEventListener('mouseleave', onUp);
    renderer.domElement.addEventListener('mousemove', onMove);

    let raf;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (globeRef.current) {
        // gentle auto-rotate
        if (!isMouseDown.current) targetRotation.current.y += 0.0004;
        globeRef.current.rotation.y += (targetRotation.current.y - globeRef.current.rotation.y) * 0.08;
        globeRef.current.rotation.x += (targetRotation.current.x - globeRef.current.rotation.x) * 0.08;
      }
      stars.rotation.y += 0.00005;
      // animate markers
      markersRef.current.forEach((g, i) => {
        const t = Date.now() * (0.001 + (g.userData.loc.count || 1) * 0.0003);
        g.children.forEach((c, idx) => {
          c.scale.setScalar(1 + Math.sin(t + i) * 0.15 * (idx === 0 ? 1 : 0.6));
          if (idx > 0) c.material.opacity = 0.5 + Math.sin(t + i) * 0.4;
        });
      });
      renderer.render(scene, camera);
    };
    loop();

    return () => {
      window.removeEventListener('resize', onResize);
      renderer.domElement.removeEventListener('mousedown', onDown);
      renderer.domElement.removeEventListener('mouseup', onUp);
      renderer.domElement.removeEventListener('mouseleave', onUp);
      renderer.domElement.removeEventListener('mousemove', onMove);
      cancelAnimationFrame(raf);
      if (containerRef.current && renderer.domElement.parentElement === containerRef.current) containerRef.current.removeChild(renderer.domElement);
      geometry.dispose();
      texture.dispose();
      renderer.dispose();
    };
  }, []);

  // update on data change
  useEffect(() => {
    if (sceneRef.current) {
      markersRef.current.forEach(m => sceneRef.current.remove(m));
      markersRef.current = [];
      // reuse addMarkers pattern by directly reconstructing
      const data = geoData || [];
      data.forEach((loc, idx) => {
        const lat = (loc.latitude * Math.PI) / 180;
        const lon = (loc.longitude * Math.PI) / 180;
        const x = Math.cos(lat) * Math.cos(lon);
        const y = Math.sin(lat);
        const z = Math.cos(lat) * Math.sin(lon);

        const group = new THREE.Group();
        const s = Math.min(0.08 + (loc.count || 1) * 0.02, 0.18);
        const sphere = new THREE.Mesh(new THREE.SphereGeometry(s, 12, 12), new THREE.MeshStandardMaterial({ color: 0xff4d4d, emissive: 0xff6b6b }));
        sphere.position.set(x, y, z);
        group.add(sphere);
        const ring = new THREE.Mesh(new THREE.TorusGeometry(s + 0.08, 0.01, 8, 32), new THREE.MeshBasicMaterial({ color: 0xff6666, transparent: true, opacity: 0.7 }));
        ring.position.set(x, y, z);
        ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(x, y, z).normalize());
        group.add(ring);
        group.userData = { loc };
        sceneRef.current.add(group);
        markersRef.current.push(group);
      });
    }
  }, [geoData]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }} />;
};

export default ThreatGlobe2;
