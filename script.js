// Smooth Scrolling using Lenis
const lenis = new Lenis({
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    direction: 'vertical',
    gestureDirection: 'vertical',
    smooth: true,
    mouseMultiplier: 1,
    smoothTouch: false,
    touchMultiplier: 2,
    infinite: true // Enables built-in infinity scroll in Lenis!
});

function raf(time) {
    lenis.raf(time);
    requestAnimationFrame(raf);
}
requestAnimationFrame(raf);

// GSAP Animations
gsap.registerPlugin(ScrollTrigger);

// Animate sections on scroll
const sections = document.querySelectorAll('.fade-in');
sections.forEach((section) => {
    gsap.fromTo(section, 
        { y: 50, opacity: 0 }, 
        { 
            y: 0, 
            opacity: 1, 
            duration: 1, 
            ease: "power3.out",
            scrollTrigger: {
                trigger: section,
                start: "top 85%",
                toggleActions: "play none none reverse"
            }
        }
    );
});

// 3D Background using Three.js
const initThreeJS = () => {
    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 30;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Create Particles
    const particlesGeometry = new THREE.BufferGeometry();
    const particlesCount = 1500;
    const posArray = new Float32Array(particlesCount * 3);

    for(let i = 0; i < particlesCount * 3; i++) {
        posArray[i] = (Math.random() - 0.5) * 100;
    }

    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));

    // Material with custom color that matches the theme
    const particlesMaterial = new THREE.PointsMaterial({
        size: 0.15,
        color: 0x00f2fe,
        transparent: true,
        opacity: 0.8,
        blending: THREE.AdditiveBlending
    });

    const particlesMesh = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particlesMesh);

    // Mouse Interaction
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX - windowHalfX);
        mouseY = (event.clientY - windowHalfY);
    });

    // Handle Resize
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // Animation Loop
    const clock = new THREE.Clock();

    const animate = () => {
        requestAnimationFrame(animate);
        const elapsedTime = clock.getElapsedTime();

        targetX = mouseX * 0.001;
        targetY = mouseY * 0.001;

        particlesMesh.rotation.y += 0.001;
        particlesMesh.rotation.x += 0.0005;

        // Smooth mouse follow
        particlesMesh.rotation.y += 0.05 * (targetX - particlesMesh.rotation.y);
        particlesMesh.rotation.x += 0.05 * (targetY - particlesMesh.rotation.x);

        // Wave effect
        const positions = particlesGeometry.attributes.position.array;
        for(let i = 0; i < particlesCount; i++) {
            const i3 = i * 3;
            const x = particlesGeometry.attributes.position.array[i3];
            // Animate Z based on X and Time
            particlesGeometry.attributes.position.array[i3 + 2] = Math.sin(elapsedTime + x) * 2;
        }
        particlesGeometry.attributes.position.needsUpdate = true;

        renderer.render(scene, camera);
    };

    animate();
};

initThreeJS();

// Manual Infinity Scroll Backup (if Lenis infinite gets disabled or acts weird with fixed heights)
// We duplicate the content wrapper to create a seamless loop
const scrollContainer = document.querySelector('.scroll-container');
const contentWrapper = document.querySelector('.content-wrapper');
const clone = contentWrapper.cloneNode(true);
scrollContainer.appendChild(clone);

// Re-initialize GSAP on the cloned elements
const clonedSections = clone.querySelectorAll('.fade-in');
clonedSections.forEach((section) => {
    gsap.fromTo(section, 
        { y: 50, opacity: 0 }, 
        { 
            y: 0, 
            opacity: 1, 
            duration: 1, 
            ease: "power3.out",
            scrollTrigger: {
                trigger: section,
                start: "top 85%",
                toggleActions: "play none none reverse"
            }
        }
    );
});
