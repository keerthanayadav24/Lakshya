document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('goal-form');
    const statusArea = document.getElementById('status-area');

    if (form && statusArea) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const title = formData.get('title');
            const deadline = formData.get('deadline');

            statusArea.innerHTML = `
                <p class="status-message success">
                    ✅ Phase 1 Placeholder: Goal "${title}" with deadline "${deadline}" captured locally.
                    Full LLM task breakdown and calendar integration will be enabled in future phases.
                </p>
            `;
        });
    }
});
