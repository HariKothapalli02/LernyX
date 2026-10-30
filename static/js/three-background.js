// Three.js Interactive Background: Elegant Royal Purple & Violet Neural Constellation
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('canvas-container');
    if (!container) return;

    // Scene Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0xf8fafc, 0.0007); // Soft canvas fog

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 2000);
    camera.position.z = 1000;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Particles Setup
    const particleCount = 320;
    const particles = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = [];

    // Initial positions
    for (let i = 0; i < particleCount * 3; i += 3) {
        positions[i] = (Math.random() - 0.5) * 2000;     // x
        positions[i + 1] = (Math.random() - 0.5) * 2000; // y
        positions[i + 2] = (Math.random() - 0.5) * 2000; // z

        velocities.push({
            x: (Math.random() - 0.5) * 0.4,
            y: (Math.random() - 0.5) * 0.4,
            z: (Math.random() - 0.5) * 0.4
        });
    }

    particles.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Material: Royal Purple & Violet Glowing Points
    const material = new THREE.PointsMaterial({
        color: 0x7c3aed, // Royal Purple
        size: 3.5,
        transparent: true,
        opacity: 0.65,
        blending: THREE.NormalBlending
    });

    const particleSystem = new THREE.Points(particles, material);
    scene.add(particleSystem);

    // Mouse Interaction
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX - windowHalfX) * 0.35;
        mouseY = (event.clientY - windowHalfY) * 0.35;
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        targetX = mouseX * 0.0008;
        targetY = mouseY * 0.0008;

        // Smooth rotation based on mouse
        particleSystem.rotation.y += 0.0008 + (targetX - particleSystem.rotation.y) * 0.04;
        particleSystem.rotation.x += 0.0008 + (targetY - particleSystem.rotation.x) * 0.04;

        // Update positions
        const posArray = particleSystem.geometry.attributes.position.array;

        for (let i = 0; i < particleCount; i++) {
            const i3 = i * 3;

            posArray[i3] += velocities[i].x;
            posArray[i3 + 1] += velocities[i].y;
            posArray[i3 + 2] += velocities[i].z;

            // Bounce back
            if (posArray[i3] < -1000 || posArray[i3] > 1000) velocities[i].x *= -1;
            if (posArray[i3 + 1] < -1000 || posArray[i3 + 1] > 1000) velocities[i].y *= -1;
            if (posArray[i3 + 2] < -1000 || posArray[i3 + 2] > 1000) velocities[i].z *= -1;
        }

        particleSystem.geometry.attributes.position.needsUpdate = true;
        renderer.render(scene, camera);
    }

    // Handle Resize
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    animate();
});
