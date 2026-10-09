/**
 * Lakshya Student Dashboard Client Application
 * Handles API contracts, proposal lifecycle, confirmation modals, and safe DOM rendering.
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const syllabusForm = document.getElementById('syllabus-form');
    const goalTitleInput = document.getElementById('goal-title');
    const goalDeadlineInput = document.getElementById('goal-deadline');
    const syllabusTextInput = document.getElementById('syllabus-text');
    const charCounter = document.getElementById('char-counter');
    const generateBtn = document.getElementById('generate-btn');
    const btnSpinner = document.getElementById('btn-spinner');
    const btnText = document.getElementById('btn-text');
    const formFeedback = document.getElementById('form-feedback');

    const tasksContainer = document.getElementById('tasks-container');
    const taskCountBadge = document.getElementById('task-count-badge');
    const scheduleContainer = document.getElementById('schedule-container');
    const scheduleCountBadge = document.getElementById('schedule-count-badge');

    const detectReplanBtn = document.getElementById('detect-replan-btn');
    const proposalsFeedback = document.getElementById('proposals-feedback');
    const proposalsContainer = document.getElementById('proposals-container');

    const refreshAuditBtn = document.getElementById('refresh-audit-btn');
    const auditsContainer = document.getElementById('audits-container');

    const calendarStatusBadge = document.getElementById('calendar-status');
    const calendarStatusText = document.getElementById('calendar-status-text');

    const confirmModal = document.getElementById('confirm-modal');
    const confirmApproveBtn = document.getElementById('confirm-approve-btn');
    const cancelApproveBtn = document.getElementById('cancel-approve-btn');

    // Global Active State
    let currentGoalId = null;
    let pendingApprovalProposalId = null;

    // Helper: Default Deadline (7 days from now)
    function setDefaultDeadline() {
        const now = new Date();
        now.setDate(now.getDate() + 7);
        const isoString = now.toISOString().slice(0, 16);
        if (goalDeadlineInput && !goalDeadlineInput.value) {
            goalDeadlineInput.value = isoString;
        }
    }
    setDefaultDeadline();

    // Helper: Character Counter
    if (syllabusTextInput && charCounter) {
        const updateCharCount = () => {
            const count = syllabusTextInput.value.length;
            charCounter.textContent = `${count.toLocaleString()} / 50,000 characters`;
        };
        syllabusTextInput.addEventListener('input', updateCharCount);
        updateCharCount();
    }

    if (syllabusForm) {
        syllabusForm.addEventListener('reset', () => {
            clearFeedback(formFeedback);
            setTimeout(() => {
                if (charCounter) {
                    charCounter.textContent = '0 / 50,000 characters';
                }
            }, 0);
        });
    }

    // Shared Fetch Helper
    async function fetchAPI(url, options = {}) {
        const defaultHeaders = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        };
        const config = {
            ...options,
            headers: {
                ...defaultHeaders,
                ...(options.headers || {}),
            },
        };

        const response = await fetch(url, config);
        let data = null;

        try {
            data = await response.json();
        } catch (e) {
            // Empty or non-JSON body
        }

        if (!response.ok) {
            const errorMsg = data && data.detail ? data.detail : `Request failed with status ${response.status}`;
            throw new Error(errorMsg);
        }

        return data;
    }

    // Helper: Display Feedback Box
    function showFeedback(element, message, isSuccess = false) {
        if (!element) return;
        element.hidden = false;
        element.className = `feedback-box ${isSuccess ? 'feedback-success' : 'feedback-error'}`;
        element.textContent = message;
    }

    function clearFeedback(element) {
        if (!element) return;
        element.hidden = true;
        element.textContent = '';
    }

    // 1. Calendar Connection Status
    async function checkCalendarStatus() {
        try {
            const data = await fetchAPI('/api/calendar/status');
            if (data.connected) {
                calendarStatusBadge.className = 'status-badge status-connected';
                calendarStatusText.textContent = 'Calendar Connected';
            } else {
                calendarStatusBadge.className = 'status-badge status-disconnected';
                calendarStatusText.textContent = 'Calendar Unlinked';
            }
        } catch (err) {
            calendarStatusBadge.className = 'status-badge status-disconnected';
            calendarStatusText.textContent = 'Calendar Offline';
        }
    }

    // 2. Syllabus Form Submission (Plan Creator)
    if (syllabusForm) {
        syllabusForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            clearFeedback(formFeedback);

            const title = goalTitleInput.value.trim();
            const syllabusText = syllabusTextInput.value.trim();
            const rawDeadline = goalDeadlineInput.value;

            if (!title) {
                showFeedback(formFeedback, 'Please enter a goal title.');
                return;
            }
            if (!syllabusText) {
                showFeedback(formFeedback, 'Please paste your syllabus text.');
                return;
            }
            if (!rawDeadline) {
                showFeedback(formFeedback, 'Please select a target deadline.');
                return;
            }

            const deadlineDate = new Date(rawDeadline);
            if (isNaN(deadlineDate.getTime()) || deadlineDate <= new Date()) {
                showFeedback(formFeedback, 'Deadline must be a valid future date and time.');
                return;
            }

            // Lock UI & spinner
            generateBtn.disabled = true;
            btnSpinner.hidden = false;
            btnText.textContent = 'Generating Plan...';

            try {
                const payload = {
                    title: title,
                    syllabus_text: syllabusText,
                    deadline: deadlineDate.toISOString(),
                };

                const data = await fetchAPI('/api/goals', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });

                currentGoalId = data.goal.id;
                showFeedback(formFeedback, `Study plan generated successfully for "${data.goal.title}"!`, true);
                
                renderTasks(data.tasks);
                renderSchedule(data.plan ? data.plan.blocks : []);
                loadProposals();
                loadAudits();

            } catch (err) {
                showFeedback(formFeedback, err.message || 'Failed to generate study plan.');
            } finally {
                generateBtn.disabled = false;
                btnSpinner.hidden = true;
                btnText.textContent = 'Generate Study Plan';
            }
        });
    }

    // 3. Render Tasks
    function renderTasks(tasks) {
        tasksContainer.replaceChildren();
        if (!tasks || tasks.length === 0) {
            taskCountBadge.textContent = '0 Tasks';
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No study tasks generated yet.';
            tasksContainer.appendChild(empty);
            return;
        }

        taskCountBadge.textContent = `${tasks.length} Tasks`;

        tasks.forEach((t) => {
            const card = document.createElement('div');
            card.className = 'task-card';

            const title = document.createElement('div');
            title.className = 'task-title';
            title.textContent = t.title;

            const meta = document.createElement('div');
            meta.className = 'task-meta';

            const duration = document.createElement('span');
            duration.textContent = `⏱️ ${t.estimated_minutes} mins`;

            const deadline = document.createElement('span');
            const dDate = new Date(t.deadline);
            deadline.textContent = `📅 ${dDate.toLocaleDateString()}`;

            meta.appendChild(duration);
            meta.appendChild(deadline);

            card.appendChild(title);

            if (t.description) {
                const desc = document.createElement('div');
                desc.className = 'task-desc';
                desc.textContent = t.description;
                card.appendChild(desc);
            }

            card.appendChild(meta);
            tasksContainer.appendChild(card);
        });
    }

    // 4. Render Schedule Timeline
    function renderSchedule(blocks) {
        scheduleContainer.replaceChildren();
        if (!blocks || blocks.length === 0) {
            scheduleCountBadge.textContent = '0 Blocks';
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No study blocks scheduled.';
            scheduleContainer.appendChild(empty);
            return;
        }

        scheduleCountBadge.textContent = `${blocks.length} Blocks`;

        blocks.forEach((b) => {
            const item = document.createElement('div');
            item.className = 'timeline-item';

            const info = document.createElement('div');
            info.className = 'timeline-info';

            const title = document.createElement('h4');
            title.textContent = b.title;

            const time = document.createElement('div');
            time.className = 'timeline-time';

            const startDate = new Date(b.start);
            const endDate = new Date(b.end);
            const dateStr = startDate.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
            const startTimeStr = startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const endTimeStr = endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            time.textContent = `${dateStr} • ${startTimeStr} – ${endTimeStr}`;

            info.appendChild(title);
            info.appendChild(time);

            const duration = document.createElement('div');
            duration.className = 'timeline-duration';
            duration.textContent = '50m Session';

            item.appendChild(info);
            item.appendChild(duration);
            scheduleContainer.appendChild(item);
        });
    }

    // 5. Load & Render Agent Proposals
    async function loadProposals() {
        try {
            const proposals = await fetchAPI('/api/proposals');
            renderProposals(proposals);
        } catch (err) {
            proposalsContainer.replaceChildren();
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'Failed to load proposals.';
            proposalsContainer.appendChild(empty);
        }
    }

    function renderProposals(proposals) {
        proposalsContainer.replaceChildren();
        if (!proposals || proposals.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No proposal history found.';
            proposalsContainer.appendChild(empty);
            return;
        }

        proposals.forEach((p) => {
            const card = document.createElement('div');
            card.className = 'proposal-card';

            // Proposal Header
            const header = document.createElement('div');
            header.className = 'proposal-header';

            const reason = document.createElement('div');
            reason.className = 'proposal-reason';
            reason.textContent = p.reason;

            const badge = document.createElement('span');
            badge.className = `badge badge-${p.status}`;
            badge.textContent = p.status.toUpperCase();

            header.appendChild(reason);
            header.appendChild(badge);

            // Blocks Comparison Grid
            const grid = document.createElement('div');
            grid.className = 'proposal-blocks-grid';

            // Old Blocks Col
            const oldCol = document.createElement('div');
            oldCol.className = 'block-col';
            const oldH5 = document.createElement('h5');
            oldH5.textContent = `Missed/Old Blocks (${p.old_blocks.length})`;
            oldCol.appendChild(oldH5);

            if (p.old_blocks.length === 0) {
                const pEmpty = document.createElement('p');
                pEmpty.className = 'subtitle-text';
                pEmpty.textContent = 'None';
                oldCol.appendChild(pEmpty);
            } else {
                p.old_blocks.forEach((ob) => {
                    const chip = document.createElement('div');
                    chip.className = 'block-chip block-chip-old';
                    chip.textContent = ob.title;
                    oldCol.appendChild(chip);
                });
            }

            // New Blocks Col
            const newCol = document.createElement('div');
            newCol.className = 'block-col';
            const newH5 = document.createElement('h5');
            newH5.textContent = `Proposed Replans (${p.new_blocks.length})`;
            newCol.appendChild(newH5);

            if (p.new_blocks.length === 0) {
                const pEmpty = document.createElement('p');
                pEmpty.className = 'subtitle-text';
                pEmpty.textContent = 'None';
                newCol.appendChild(pEmpty);
            } else {
                p.new_blocks.forEach((nb) => {
                    const chip = document.createElement('div');
                    chip.className = 'block-chip block-chip-new';
                    const nDate = new Date(nb.start);
                    chip.textContent = `${nb.title} (${nDate.toLocaleDateString()})`;
                    newCol.appendChild(chip);
                });
            }

            grid.appendChild(oldCol);
            grid.appendChild(newCol);

            // Action Buttons
            const actions = document.createElement('div');
            actions.className = 'proposal-actions';

            if (p.status === 'pending') {
                const approveBtn = document.createElement('button');
                approveBtn.className = 'btn btn-primary btn-sm';
                approveBtn.textContent = 'Approve & Mutate Calendar';
                approveBtn.addEventListener('click', () => openApproveModal(p.id));

                const rejectBtn = document.createElement('button');
                rejectBtn.className = 'btn btn-danger btn-sm';
                rejectBtn.textContent = 'Reject Proposal';
                rejectBtn.addEventListener('click', () => handleReject(p.id));

                actions.appendChild(approveBtn);
                actions.appendChild(rejectBtn);
            } else if (p.status === 'applied' || p.status === 'partially_applied') {
                const undoBtn = document.createElement('button');
                undoBtn.className = 'btn btn-secondary btn-sm';
                undoBtn.textContent = 'Undo Proposal';
                undoBtn.addEventListener('click', () => handleUndo(p.id));
                actions.appendChild(undoBtn);
            }

            card.appendChild(header);
            card.appendChild(grid);
            if (actions.children.length > 0) {
                card.appendChild(actions);
            }

            proposalsContainer.appendChild(card);
        });
    }

    // 6. Proposal Creation Trigger
    if (detectReplanBtn) {
        detectReplanBtn.addEventListener('click', async () => {
            clearFeedback(proposalsFeedback);
            if (!currentGoalId) {
                // Fetch latest goal if not set
                try {
                    const latest = await fetchAPI('/api/goals/latest');
                    currentGoalId = latest.goal.id;
                } catch (e) {
                    showFeedback(proposalsFeedback, 'Please create a study plan first before proposing a replan.');
                    return;
                }
            }

            detectReplanBtn.disabled = true;
            try {
                const proposal = await fetchAPI(`/api/proposals?goal_id=${encodeURIComponent(currentGoalId)}`, {
                    method: 'POST',
                });
                showFeedback(proposalsFeedback, `Proposal "${proposal.id}" created cleanly. Calendar is NOT mutated until you approve!`, true);
                loadProposals();
                loadAudits();
            } catch (err) {
                showFeedback(proposalsFeedback, err.message || 'Failed to generate proposal.');
            } finally {
                detectReplanBtn.disabled = false;
            }
        });
    }

    // 7. Modal Confirmation & Approval Execution
    function openApproveModal(proposalId) {
        pendingApprovalProposalId = proposalId;
        confirmModal.hidden = false;
    }

    function closeApproveModal() {
        pendingApprovalProposalId = null;
        confirmModal.hidden = true;
    }

    if (cancelApproveBtn) {
        cancelApproveBtn.addEventListener('click', closeApproveModal);
    }

    if (confirmApproveBtn) {
        confirmApproveBtn.addEventListener('click', async () => {
            if (!pendingApprovalProposalId) return;
            const pid = pendingApprovalProposalId;
            closeApproveModal();

            clearFeedback(proposalsFeedback);
            try {
                const result = await fetchAPI(`/api/proposals/${encodeURIComponent(pid)}/approve`, {
                    method: 'POST',
                    body: JSON.stringify({ approved: true }),
                });

                if (result.status === 'applied') {
                    showFeedback(proposalsFeedback, `Proposal ${pid} approved and applied to Google Calendar!`, true);
                } else {
                    showFeedback(proposalsFeedback, `Proposal ${pid} status: ${result.status}`, true);
                }

                loadProposals();
                loadAudits();
            } catch (err) {
                showFeedback(proposalsFeedback, err.message || 'Failed to approve proposal.');
                loadProposals();
            }
        });
    }

    // 8. Rejection Handler
    async function handleReject(proposalId) {
        clearFeedback(proposalsFeedback);
        try {
            await fetchAPI(`/api/proposals/${encodeURIComponent(proposalId)}/reject`, {
                method: 'POST',
            });
            showFeedback(proposalsFeedback, `Proposal ${proposalId} rejected. Zero calendar changes were made.`, true);
            loadProposals();
            loadAudits();
        } catch (err) {
            showFeedback(proposalsFeedback, err.message || 'Failed to reject proposal.');
        }
    }

    // 9. Undo Handler
    async function handleUndo(proposalId) {
        clearFeedback(proposalsFeedback);
        try {
            await fetchAPI(`/api/proposals/${encodeURIComponent(proposalId)}/undo`, {
                method: 'POST',
            });
            showFeedback(proposalsFeedback, `Proposal ${proposalId} undone successfully!`, true);
            loadProposals();
            loadAudits();
        } catch (err) {
            showFeedback(proposalsFeedback, err.message || 'Failed to undo proposal.');
        }
    }

    // 10. Audit History Log
    async function loadAudits() {
        try {
            const audits = await fetchAPI('/api/audits');
            renderAudits(audits);
        } catch (err) {
            auditsContainer.replaceChildren();
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'Failed to load audit entries.';
            auditsContainer.appendChild(empty);
        }
    }

    function renderAudits(audits) {
        auditsContainer.replaceChildren();
        if (!audits || audits.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No activity logged yet.';
            auditsContainer.appendChild(empty);
            return;
        }

        const table = document.createElement('table');
        table.className = 'audit-table';

        const thead = document.createElement('thead');
        const trHead = document.createElement('tr');
        ['Action', 'Timestamp', 'Details'].forEach((h) => {
            const th = document.createElement('th');
            th.textContent = h;
            trHead.appendChild(th);
        });
        thead.appendChild(trHead);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        audits.slice().reverse().forEach((entry) => {
            const tr = document.createElement('tr');

            const tdAction = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.textContent = entry.action;
            tdAction.appendChild(badge);

            const tdTime = document.createElement('td');
            const tDate = new Date(entry.timestamp);
            tdTime.textContent = tDate.toLocaleString();

            const tdDetails = document.createElement('td');
            tdDetails.textContent = JSON.stringify(entry.details);

            tr.appendChild(tdAction);
            tr.appendChild(tdTime);
            tr.appendChild(tdDetails);
            tbody.appendChild(tr);
        });

        table.appendChild(tbody);
        auditsContainer.appendChild(table);
    }

    if (refreshAuditBtn) {
        refreshAuditBtn.addEventListener('click', loadAudits);
    }

    // Initial Load Sequence
    async function initDashboard() {
        checkCalendarStatus();
        loadProposals();
        loadAudits();

        // Attempt loading existing goal if available
        try {
            const latest = await fetchAPI('/api/goals/latest');
            if (latest && latest.goal) {
                currentGoalId = latest.goal.id;
                goalTitleInput.value = latest.goal.title;
                syllabusTextInput.value = latest.goal.syllabus_text;
                if (charCounter && syllabusTextInput) {
                    const count = syllabusTextInput.value.length;
                    charCounter.textContent = `${count.toLocaleString()} / 50,000 characters`;
                }

                renderTasks(latest.tasks);
                renderSchedule(latest.plan ? latest.plan.blocks : []);
            }
        } catch (e) {
            // No goal created yet
        }
    }

    initDashboard();
});
