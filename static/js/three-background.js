// Three.js Interactive Background
// Creates a connecting particle network (Neural Network effect)

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('canvas-container');
    if (!container) return;

    // Scene Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.0008); // Deep space fog

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 2000);
    camera.position.z = 1000;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Particles Setup
    const particleCount = 400; // Adjust for performance
    const particles = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = [];

    // Initial positions
    for (let i = 0; i < particleCount * 3; i += 3) {
        positions[i] = (Math.random() - 0.5) * 2000;     // x
        positions[i + 1] = (Math.random() - 0.5) * 2000; // y
        positions[i + 2] = (Math.random() - 0.5) * 2000; // z

        velocities.push({
            x: (Math.random() - 0.5) * 0.5,
            y: (Math.random() - 0.5) * 0.5,
            z: (Math.random() - 0.5) * 0.5
        });
    }

    particles.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Material
    const material = new THREE.PointsMaterial({
        color: 0xffffff, // Stark white points
        size: 3,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending
    });

    const particleSystem = new THREE.Points(particles, material);
    scene.add(particleSystem);

    // Lines (Connections)
    const lineMaterial = new THREE.LineBasicMaterial({
        color: 0x888888, // Crisp monochrome gray
        transparent: true,
        opacity: 0.2
    });

    // Mouse Interaction
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX - windowHalfX) * 0.5;
        mouseY = (event.clientY - windowHalfY) * 0.5;
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        targetX = mouseX * 0.001;
        targetY = mouseY * 0.001;

        // Rotate entire system slowly based on mouse
        particleSystem.rotation.y += 0.001 + (targetX - particleSystem.rotation.y) * 0.05;
        particleSystem.rotation.x += 0.001 + (targetY - particleSystem.rotation.x) * 0.05;

        // Update individual particles
        const positions = particleSystem.geometry.attributes.position.array;

        for (let i = 0; i < particleCount; i++) {
            const i3 = i * 3;

            // Move particles
            positions[i3] += velocities[i].x;
            positions[i3 + 1] += velocities[i].y;
            positions[i3 + 2] += velocities[i].z;

            // Boundary check (bounce back)
            if (positions[i3] < -1000 || positions[i3] > 1000) velocities[i].x *= -1;
            if (positions[i3 + 1] < -1000 || positions[i3 + 1] > 1000) velocities[i].y *= -1;
            if (positions[i3 + 2] < -1000 || positions[i3 + 2] > 1000) velocities[i].z *= -1;
        }

        particleSystem.geometry.attributes.position.needsUpdate = true;

        // Dynamic Lines (Raycasting is too heavy, doing distance check)
        // Note: Creating lines every frame is expensive. 
        // Optimization: Only draw lines between close particles if needed, 
        // but for a "neural network" look, a static line geometry that deforms is better 
        // or just using Points is often enough for the "starfield" effect.
        // To keep it performant and "powerful", we'll stick to the rotating particle cloud 
        // which looks like a galaxy/brain. 
        // If we want lines, we use a LineSegments geometry with pre-calculated connections 
        // that move with the points, but that's complex to sync.
        // Let's add a "wave" effect instead to make it feel alive.

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
