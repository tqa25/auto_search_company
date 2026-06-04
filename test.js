(function() {
      let isInspectorActive = false;
      let highlightedElement = null;

      // Add toggle button
      const toggleBtn = document.createElement('button');
      toggleBtn.innerHTML = '<i data-lucide="mouse-pointer-click"></i> Inspector Mode';
      Object.assign(toggleBtn.style, {
        position: 'fixed', bottom: '20px', right: '20px', zIndex: 10000,
        background: 'var(--accent)', color: 'white', border: 'none',
        padding: '10px 16px', borderRadius: '20px', display: 'flex', gap: '8px',
        alignItems: 'center', cursor: 'pointer', boxShadow: '0 4px 12px rgba(168,85,247,0.3)',
        fontFamily: 'var(--font)', fontWeight: '500', fontSize: '14px', transition: 'background 0.2s'
      });
      console.log('hi');
})();
