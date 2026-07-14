import React, { useEffect, useRef, useCallback, useState } from 'react';
import * as THREE from 'three';

/* ─── Lat/Lon → 3D point on unit sphere ─── */
function ll(lat, lon, r = 1) {
  const phi   = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
     r * Math.cos(phi),
     r * Math.sin(phi) * Math.sin(theta),
  );
}

/* ─── Arc between two globe points ─── */
function arc(p1, p2, segs = 60) {
  const mid = p1.clone().add(p2).multiplyScalar(0.5);
  mid.normalize().multiplyScalar(1 + 0.15 + p1.distanceTo(p2) * 0.2);
  return new THREE.BufferGeometry().setFromPoints(
    new THREE.QuadraticBezierCurve3(p1, mid, p2).getPoints(segs)
  );
}

/* ═══════════════════════════════════════════════════
   ThreatGlobe — Stylized Wireframe/Pointcloud Globe
═══════════════════════════════════════════════════ */
const ThreatGlobe = ({ geoData = [] }) => {
  const mountRef   = useRef(null);
  const state      = useRef(null);   // { renderer, scene, camera, globe }
  const raf        = useRef(null);
  const markersRef = useRef([]);
  const arcsRef    = useRef([]);
  const orbitsRef  = useRef([]);
  const drag       = useRef({ on: false, lx: 0, ly: 0, moved: false });
  const vel        = useRef({ x: 0, y: 0 });
  
  // Tooltip state
  const [selectedNode, setSelectedNode] = useState(null);
  const selectedNodeRef = useRef(null);
  const tooltipRef = useRef(null);

  /* ── dispose a group ── */
  const drop = useCallback((g) => {
    if (!g) return;
    g.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) [].concat(o.material).forEach(m => m.dispose());
    });
    if (g.parent) g.parent.remove(g);
  }, []);

  /* ── rebuild IP markers on the globe group ── */
  const rebuild = useCallback(() => {
    if (!state.current) return;
    const { globe } = state.current;

    markersRef.current.forEach(drop);
    arcsRef.current.forEach(drop);
    markersRef.current = [];
    arcsRef.current    = [];
    setSelectedNode(null);
    selectedNodeRef.current = null;

    const pts = [];

    geoData.forEach((loc, i) => {
      const lat   = parseFloat(loc.latitude)  || 0;
      const lon   = parseFloat(loc.longitude) || 0;
      const pos   = ll(lat, lon, 1);
      pts.push(pos.clone());

      const grp = new THREE.Group();
      grp.userData.phase = Math.random() * Math.PI * 2;
      grp.userData.data = loc; // Store the original data for tooltip
      grp.userData.pos = pos;  // Store local position for projection

      /* Inner bright dot */
      const dotM = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const dot  = new THREE.Mesh(new THREE.SphereGeometry(0.012, 12, 12), dotM);
      dot.position.copy(pos.clone().multiplyScalar(1.01));
      grp.add(dot);

      /* Outer glowing halo (Used as click hitbox too) */
      const glowM = new THREE.MeshBasicMaterial({ 
        color: 0x00e5ff, 
        transparent: true, 
        opacity: 0.8,
        blending: THREE.AdditiveBlending 
      });
      // Slightly larger sphere for easier clicking
      const glow = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 16), glowM);
      glow.position.copy(dot.position);
      grp.add(glow);
      grp.userData.glowM = glowM;
      grp.userData.hitbox = glow; // save reference for raycasting
      
      /* Expanding pulse ring */
      const waveM = new THREE.MeshBasicMaterial({ 
        color: 0x00e5ff, 
        transparent: true, 
        opacity: 0,
        blending: THREE.AdditiveBlending 
      });
      const wave = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.002, 12, 32), waveM);
      wave.position.copy(dot.position);
      wave.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), pos.clone().normalize());
      grp.add(wave);
      grp.userData.waveM = waveM;
      grp.userData.wave  = wave;

      globe.add(grp);
      markersRef.current.push(grp);
    });

    /* Thin arcs between threat locations */
    if (pts.length > 1) {
      for (let i = 0; i < pts.length; i++) {
        const j = (i + 1) % pts.length;
        const aM = new THREE.LineBasicMaterial({ 
          color: 0x00e5ff, 
          transparent: true, 
          opacity: 0.25,
          blending: THREE.AdditiveBlending
        });
        const ln = new THREE.Line(arc(pts[i], pts[j]), aM);
        ln.userData.phase = Math.random() * Math.PI * 2;
        globe.add(ln);
        arcsRef.current.push(ln);
      }
    }
  }, [geoData, drop]);

  /* ── Setup Three.js scene (runs once) ── */
  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    /* Renderer */
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, el.clientWidth / el.clientHeight, 0.1, 1000);
    camera.position.z = 2.8;

    /* Globe group — everything that rotates together */
    const globe = new THREE.Group();
    scene.add(globe);

    /* Very faint transparent inner sphere */
    const sphereGeo = new THREE.SphereGeometry(0.99, 64, 64);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0x000205,
      transparent: true,
      opacity: 0.85,
    });
    globe.add(new THREE.Mesh(sphereGeo, sphereMat));

    /* ─── Shader-based Point Cloud for Continents ─── */
    // Increased N from 70000 to 180000 to fill gaps, made points larger
    const N  = 180000;
    const dv = [];
    const uvs = [];
    
    for (let i = 0; i < N; i++) {
      const phi   = Math.acos(1 - 2 * i / N);
      const theta = Math.PI * (1 + Math.sqrt(5)) * i;
      
      const lat = 90 - phi * (180 / Math.PI);
      const lon = ((theta * (180 / Math.PI)) % 360) - 180;
      
      const v = ll(lat, lon, 1.0);
      dv.push(v.x, v.y, v.z);
      
      const u = (lon + 180) / 360;
      const v_uv = (lat + 90) / 180;
      uvs.push(u, v_uv);
    }
    
    const dotGeo = new THREE.BufferGeometry();
    dotGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(dv), 3));
    dotGeo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));

    const textureLoader = new THREE.TextureLoader();
    const earthMap = textureLoader.load('https://unpkg.com/three-globe/example/img/earth-water.png');

    const dotMat = new THREE.ShaderMaterial({
      uniforms: {
        tEarth: { value: earthMap },
        color: { value: new THREE.Color(0x00e5ff) }
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_PointSize = 2.5; // Larger points to reduce gaps
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D tEarth;
        uniform vec3 color;
        varying vec2 vUv;
        void main() {
          vec4 texColor = texture2D(tEarth, vUv);
          if (texColor.r > 0.5) discard;
          
          float d = distance(gl_PointCoord, vec2(0.5));
          if (d > 0.5) discard;
          
          gl_FragColor = vec4(color, 0.65); // Brighter dots
        }
      `,
      transparent: true,
      blending: THREE.AdditiveBlending
    });
    
    globe.add(new THREE.Points(dotGeo, dotMat));

    /* Global Orbital Rings */
    for (let i = 0; i < 6; i++) {
      const orbitGeo = new THREE.BufferGeometry().setFromPoints(
        new THREE.Path().absarc(0, 0, 1.05 + Math.random() * 0.1, 0, Math.PI * 2).getPoints(64)
      );
      const orbitMat = new THREE.LineBasicMaterial({ 
        color: 0x00e5ff, 
        transparent: true, 
        opacity: 0.1,
        blending: THREE.AdditiveBlending
      });
      const orbit = new THREE.Line(orbitGeo, orbitMat);
      orbit.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);
      orbit.userData = { 
        rx: (Math.random() - 0.5) * 0.002, 
        ry: (Math.random() - 0.5) * 0.002, 
        rz: (Math.random() - 0.5) * 0.002 
      };
      globe.add(orbit);
      orbitsRef.current.push(orbit);
    }

    state.current = { renderer, scene, camera, globe };

    /* ── Raycaster for Clicks ── */
    const raycaster = new THREE.Raycaster();
    const mousePos = new THREE.Vector2();

    const handleClick = (e) => {
      if (drag.current.moved) return; // Ignore clicks if user was dragging
      
      const rect = el.getBoundingClientRect();
      const clientX = e.changedTouches ? e.changedTouches[0].clientX : e.clientX;
      const clientY = e.changedTouches ? e.changedTouches[0].clientY : e.clientY;
      
      mousePos.x = ((clientX - rect.left) / rect.width) * 2 - 1;
      mousePos.y = -((clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mousePos, camera);
      
      // Raycast against the glow hitboxes of markers
      const hitboxes = markersRef.current.map(g => g.userData.hitbox);
      const intersects = raycaster.intersectObjects(hitboxes);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const grp = hit.parent; // the group holding this marker
        setSelectedNode(grp.userData.data);
        selectedNodeRef.current = grp;
      } else {
        setSelectedNode(null);
        selectedNodeRef.current = null;
      }
    };

    /* ── Mouse / touch drag ── */
    const dom = renderer.domElement;
    const onDown = e => {
      drag.current = { on: true, lx: e.clientX, ly: e.clientY, moved: false };
      vel.current  = { x: 0, y: 0 };
    };
    const onUp   = e => { 
      if (drag.current.on) handleClick(e); // Trigger click check on mouse up
      drag.current.on = false; 
    };
    const onMove = e => {
      if (!drag.current.on) return;
      drag.current.moved = true; // Mark as dragging
      const dx = e.clientX - drag.current.lx;
      const dy = e.clientY - drag.current.ly;
      vel.current = { x: dy * 0.005, y: dx * 0.005 };
      globe.rotation.x += dy * 0.005;
      globe.rotation.y += dx * 0.005;
      drag.current.lx = e.clientX;
      drag.current.ly = e.clientY;
    };
    const onTouchStart = e => {
      const t = e.touches[0];
      drag.current = { on: true, lx: t.clientX, ly: t.clientY, moved: false };
      vel.current  = { x: 0, y: 0 };
    };
    const onTouchEnd   = e => { 
      if (drag.current.on) handleClick(e); 
      drag.current.on = false; 
    };
    const onTouchMove  = e => {
      if (!drag.current.on) return;
      drag.current.moved = true;
      const t  = e.touches[0];
      const dx = t.clientX - drag.current.lx;
      const dy = t.clientY - drag.current.ly;
      vel.current = { x: dy * 0.004, y: dx * 0.004 };
      globe.rotation.x += dy * 0.004;
      globe.rotation.y += dx * 0.004;
      drag.current.lx = t.clientX;
      drag.current.ly = t.clientY;
    };
    
    dom.addEventListener('mousedown', onDown);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('mousemove', onMove);
    dom.addEventListener('touchstart', onTouchStart, { passive: false });
    dom.addEventListener('touchend', onTouchEnd);
    dom.addEventListener('touchmove', onTouchMove, { passive: false });

    /* ── Resize ── */
    const onResize = () => {
      if (!el) return;
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };
    window.addEventListener('resize', onResize);

    /* ── Animation loop ── */
    const clock = new THREE.Clock();
    const tick  = () => {
      raf.current = requestAnimationFrame(tick);
      const t = clock.getElapsedTime();

      /* Auto-rotate when idle */
      if (!drag.current.on) {
        globe.rotation.y += 0.001;
        globe.rotation.x += vel.current.x;
        globe.rotation.y += vel.current.y;
        vel.current.x *= 0.92;
        vel.current.y *= 0.92;
      }

      /* Animate orbital rings slowly */
      orbitsRef.current.forEach(orbit => {
        orbit.rotation.x += orbit.userData.rx;
        orbit.rotation.y += orbit.userData.ry;
        orbit.rotation.z += orbit.userData.rz;
      });

      /* Animate markers */
      markersRef.current.forEach(g => {
        const { phase, glowM, waveM, wave } = g.userData;
        const p = t * 2.0 + phase;

        if (glowM) glowM.opacity = 0.4 + 0.4 * Math.abs(Math.sin(p));
        
        if (waveM && wave) {
          const wt = (t * 0.8 + phase * 0.5) % 2.0;
          wave.scale.setScalar(1 + wt * 2.0);
          waveM.opacity = Math.max(0, 0.5 * (1 - wt / 2.0));
        }
      });

      /* Animate arcs */
      arcsRef.current.forEach(ln => {
        const p = t * 1.5 + ln.userData.phase;
        ln.material.opacity = Math.max(0, 0.3 * Math.sin(p));
      });
      
      /* Update Tooltip position */
      if (selectedNodeRef.current && tooltipRef.current) {
        // Project local 3D position to 2D screen coordinates
        const pos = selectedNodeRef.current.userData.pos.clone();
        // Apply globe rotation to the local position
        pos.applyMatrix4(globe.matrixWorld);
        pos.project(camera);
        
        // Hide tooltip if the node rotates behind the globe
        if (pos.z > 1) {
          tooltipRef.current.style.opacity = '0';
        } else {
          tooltipRef.current.style.opacity = '1';
          const x = (pos.x * 0.5 + 0.5) * el.clientWidth;
          const y = (-(pos.y * 0.5) + 0.5) * el.clientHeight;
          
          tooltipRef.current.style.transform = `translate(-50%, calc(-100% - 15px))`;
          tooltipRef.current.style.left = `${x}px`;
          tooltipRef.current.style.top = `${y}px`;
        }
      }

      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf.current);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('resize', onResize);
      dom.removeEventListener('mousedown', onDown);
      dom.removeEventListener('touchstart', onTouchStart);
      dom.removeEventListener('touchend', onTouchEnd);
      dom.removeEventListener('touchmove', onTouchMove);
      markersRef.current.forEach(drop);
      arcsRef.current.forEach(drop);
      orbitsRef.current.forEach(drop);
      sphereGeo.dispose(); sphereMat.dispose();
      dotGeo.dispose();    dotMat.dispose();
      renderer.dispose();
      if (el.contains(dom)) el.removeChild(dom);
      state.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* Rebuild markers whenever geoData changes */
  useEffect(() => { rebuild(); }, [rebuild]);

  return (
    <div
      ref={mountRef}
      style={{
        width: '100%', height: '100%', position: 'relative',
        cursor: 'grab',
        background: '#000000',
        userSelect: 'none',
        overflow: 'hidden'
      }}
    >
      {/* 3D Tooltip Overlay */}
      {selectedNode && (
        <div 
          ref={tooltipRef}
          style={{
            position: 'absolute',
            pointerEvents: 'none',
            background: 'rgba(0, 15, 30, 0.85)',
            border: '1px solid rgba(0, 229, 255, 0.4)',
            boxShadow: '0 4px 15px rgba(0, 0, 0, 0.5), 0 0 10px rgba(0, 229, 255, 0.1)',
            borderRadius: '6px',
            padding: '0.6rem 0.8rem',
            color: '#fff',
            fontFamily: 'monospace',
            fontSize: '0.7rem',
            minWidth: '160px',
            backdropFilter: 'blur(4px)',
            transition: 'opacity 0.15s ease',
            zIndex: 10
          }}
        >
          {/* Tooltip triangle pointer */}
          <div style={{
            position: 'absolute',
            bottom: '-6px',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '6px solid transparent',
            borderRight: '6px solid transparent',
            borderTop: '6px solid rgba(0, 229, 255, 0.4)'
          }}/>
          <div style={{
            position: 'absolute',
            bottom: '-5px',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '5px solid transparent',
            borderRight: '5px solid transparent',
            borderTop: '5px solid rgba(0, 15, 30, 0.95)'
          }}/>
          
          <div style={{ color: '#00e5ff', fontWeight: 'bold', marginBottom: '4px', textTransform: 'uppercase', borderBottom: '1px solid rgba(0,229,255,0.2)', paddingBottom: '3px' }}>
            Threat Origin
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 8px', marginTop: '6px' }}>
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>IP:</span>
            <span>{selectedNode.ip || 'Masked / Aggregated'}</span>
            
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>LOC:</span>
            <span style={{ color: '#fff' }}>{selectedNode.country || 'Unknown'}</span>
            
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>ATK:</span>
            <span style={{ color: '#ff3c3c', fontWeight: 'bold' }}>{selectedNode.count} packets</span>
          </div>
        </div>
      )}

      {/* LIVE badge */}
      <div style={{
        position: 'absolute', top: '1rem', left: '1rem',
        display: 'flex', alignItems: 'center', gap: '0.6rem',
        pointerEvents: 'none',
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: '#00e5ff',
          boxShadow: '0 0 10px 3px rgba(0,229,255,0.4)',
          animation: 'glbPulse 1.5s ease-in-out infinite',
        }} />
        <span style={{ fontSize: '0.7rem', fontFamily: 'monospace', color: '#00e5ff', letterSpacing: '0.15em', fontWeight: 'bold' }}>
          CONNECTED SECURITY
        </span>
      </div>

      {/* Drag hint */}
      <div style={{
        position: 'absolute', bottom: '1rem', right: '1rem',
        fontSize: '0.65rem', color: 'rgba(0,229,255,0.5)',
        fontFamily: 'monospace', pointerEvents: 'none',
        letterSpacing: '0.1em'
      }}>
        DRAG TO ROTATE
      </div>

      <style>{`@keyframes glbPulse{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
    </div>
  );
};

export default ThreatGlobe;
