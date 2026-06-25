(function () {
    const bootstrap = window.APP_BOOTSTRAP || {};
    const page = bootstrap.page || document.body.dataset.page || "home";
    let notifications = bootstrap.notifications || [];
    let threads = normalizeThreads(bootstrap.message_threads || []);

    let activeThreadIndex = 0;
    let messageRefreshTimer = null;
    let messageToneTimer = null;
    let messageToneRequestId = 0;
    let lastMessageToneBody = "";
    let notificationRefreshTimer = null;
    const pendingCaptionPolls = new Map();
    let unreadNotificationCount = bootstrap.notification_unread_count || 0;
    let unreadMessageCount = bootstrap.message_unread_count || 0;
    let lastNotificationId = Math.max(0, ...notifications.map((item) => item.id || 0));
    const baseTitle = document.title;

    const panels = {
        search: document.getElementById("search-panel"),
        alerts: document.getElementById("alerts-panel"),
        messages: document.getElementById("messages-panel"),
        profile: document.getElementById("profile-modal"),
        "post-editor": document.getElementById("post-editor-modal"),
        "post-detail": document.getElementById("post-detail-modal"),
    };

    const fileInput = document.getElementById("file-input");
    const fileName = document.getElementById("file-name");
    const activityInput = document.getElementById("activity-input");
    const filePickerButton = document.querySelector(".js-open-file-picker");
    const uploadPreviewImage = document.getElementById("upload-preview-image");
    const loading = document.getElementById("loading");
    let activeProfilePostId = "";
    let activeDetailPostId = "";
    let activeDetailPost = null;

    function showToast(message) {
        const oldToast = document.querySelector(".toast");
        if (oldToast) oldToast.remove();

        const toast = document.createElement("div");
        toast.className = "toast";
        toast.textContent = message;
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 2200);
    }

    function showNotificationToast(notification) {
        const oldToast = document.querySelector(".notification-toast");
        if (oldToast) oldToast.remove();

        const toast = document.createElement(notification.link ? "a" : "div");
        toast.className = `notification-toast notification-${notification.type || "default"}`;
        if (notification.link) toast.href = notification.link;

        const icon = document.createElement("span");
        icon.className = "notification-toast-icon";
        icon.textContent = {
            like: "L",
            comment: "C",
            follow: "+",
            message: "M",
        }[notification.type] || "!";

        const copy = document.createElement("span");
        const title = document.createElement("strong");
        title.textContent = notification.title || "새 알림";
        const body = document.createElement("small");
        body.textContent = notification.body || "";
        copy.append(title, body);
        toast.append(icon, copy);
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 3600);
    }

    function setLoading(message) {
        if (!loading) return;
        const label =
            loading.querySelector(".loading-label") ||
            Array.from(loading.children).find((child) => child.tagName === "SPAN");
        if (label && message) label.textContent = message;
        loading.style.display = "flex";
    }

    function hideLoading() {
        if (loading) loading.style.display = "none";
    }

    function normalizeThreads(rawThreads) {
        return rawThreads.map((thread) => ({
            ...thread,
            messages: Array.isArray(thread.messages) ? [...thread.messages] : [],
        }));
    }

    function normalizeAiText(value) {
        let text = String(value || "");
        for (let i = 0; i < 3; i += 1) {
            const decoder = document.createElement("textarea");
            decoder.innerHTML = text;
            if (decoder.value === text) break;
            text = decoder.value;
        }

        text = text.replace(/&?\s*#\s*(x[0-9a-f]+|\d+)\s*;/gi, (_match, code) => {
            const codepoint = code.toLowerCase().startsWith("x")
                ? Number.parseInt(code.slice(1), 16)
                : Number.parseInt(code, 10);
            return Number.isFinite(codepoint) ? String.fromCodePoint(codepoint) : "";
        });
        text = text.replace(/(^|[^\w가-힣])&?\s*(quot|apos|amp|lt|gt)\s*;/gi, (_match, prefix, name) => {
            const values = { quot: '"', apos: "'", amp: "&", lt: "<", gt: ">" };
            return `${prefix}${values[name.toLowerCase()] || ""}`;
        });
        return text.replace(/[\u200b\u200c\u200d\ufeff]/g, "").replace(/[ \t]{2,}/g, " ").trim();
    }

    function meaningfulAiLength(value) {
        return normalizeAiText(value).replace(/[^0-9A-Za-z가-힣]/g, "").length;
    }

    function expandShortAiTone(value, index = 0) {
        void index;
        return normalizeAiText(value).split(/[,，]/, 1)[0].trim();
    }

    function formatShortTime(value) {
        if (!value) return "";
        const normalized = String(value).replace(" ", "T");
        const date = new Date(normalized.endsWith("Z") ? normalized : `${normalized}Z`);
        if (Number.isNaN(date.getTime())) return "";

        const now = new Date();
        const sameDay = date.toDateString() === now.toDateString();
        if (sameDay) {
            return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
        }
        return date.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
    }

    function createAvatarNode(profile) {
        const avatar = document.createElement("span");
        avatar.className = "message-avatar";
        if (profile?.display_avatar_url || profile?.avatar_url) {
            const image = document.createElement("img");
            image.src = profile.display_avatar_url || profile.avatar_url;
            image.alt = "";
            avatar.appendChild(image);
        } else {
            avatar.textContent = profile?.initial || (profile?.name || profile?.username || "?").slice(0, 1);
        }
        return avatar;
    }

    function createIcon(className) {
        const icon = document.createElement("i");
        icon.className = className;
        return icon;
    }

    function roundedRectPath(context, x, y, width, height, radius) {
        const r = Math.min(radius, width / 2, height / 2);
        context.beginPath();
        context.moveTo(x + r, y);
        context.lineTo(x + width - r, y);
        context.quadraticCurveTo(x + width, y, x + width, y + r);
        context.lineTo(x + width, y + height - r);
        context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
        context.lineTo(x + r, y + height);
        context.quadraticCurveTo(x, y + height, x, y + height - r);
        context.lineTo(x, y + r);
        context.quadraticCurveTo(x, y, x + r, y);
        context.closePath();
    }

    function drawRoundedRect(context, x, y, width, height, radius, fillStyle) {
        roundedRectPath(context, x, y, width, height, radius);
        context.fillStyle = fillStyle;
        context.fill();
    }

    function wrapCanvasText(context, text, x, y, maxWidth, lineHeight, maxLines = 3) {
        const words = String(text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
        const lines = [];
        let line = "";

        words.forEach((word) => {
            const nextLine = line ? `${line} ${word}` : word;
            if (context.measureText(nextLine).width <= maxWidth) {
                line = nextLine;
                return;
            }
            if (line) lines.push(line);
            line = word;
        });
        if (line) lines.push(line);

        lines.slice(0, maxLines).forEach((lineText, index) => {
            const output = index === maxLines - 1 && lines.length > maxLines ? `${lineText.replace(/[.。!?]+$/, "")}...` : lineText;
            context.fillText(output, x, y + index * lineHeight);
        });
        return Math.min(lines.length, maxLines) * lineHeight;
    }

    function fitCanvasText(context, text, maxWidth) {
        const value = String(text || "").trim();
        if (context.measureText(value).width <= maxWidth) return value;

        let clipped = "";
        for (const char of value) {
            if (context.measureText(`${clipped}${char}...`).width > maxWidth) break;
            clipped += char;
        }
        return `${clipped.trim()}...`;
    }

    function loadImageForCanvas(src) {
        return new Promise((resolve) => {
            if (!src) {
                resolve(null);
                return;
            }
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => resolve(null);
            image.src = src;
        });
    }

    function drawCircularImage(context, image, x, y, size) {
        context.save();
        context.beginPath();
        context.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
        context.clip();
        const scale = Math.max(size / image.width, size / image.height);
        const width = image.width * scale;
        const height = image.height * scale;
        context.drawImage(image, x + (size - width) / 2, y + (size - height) / 2, width, height);
        context.restore();
    }

    function downloadCanvas(canvas, filename) {
        const link = document.createElement("a");
        link.download = filename;
        link.href = canvas.toDataURL("image/png");
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    function createBadgeRow(badges, mode = "") {
        const row = document.createElement("span");
        row.className = `badge-row ${mode}`.trim();
        (badges || []).forEach((badge) => {
            const chip = document.createElement("span");
            chip.className = "profile-badge";
            if (badge.description) chip.title = badge.description;
            if (badge.icon) chip.appendChild(createIcon(badge.icon));
            chip.append(document.createTextNode(badge.label || ""));
            row.appendChild(chip);
        });
        return row;
    }

    function createPostAvatar(post) {
        const link = document.createElement("a");
        link.className = "avatar avatar-small avatar-ring";
        link.href = `/profile/${encodeURIComponent(post.username || "")}`;
        link.setAttribute("aria-label", `${post.pet_name || "프로필"} 프로필`);

        if (post.display_avatar_url || post.avatar_url) {
            const image = document.createElement("img");
            image.src = post.display_avatar_url || post.avatar_url;
            image.alt = post.pet_name || "";
            link.appendChild(image);
        } else {
            const initial = document.createElement("span");
            initial.textContent = post.initial || (post.pet_name || "?").slice(0, 1);
            link.appendChild(initial);
        }
        return link;
    }

    function buildNewPostCard(post) {
        const article = document.createElement("article");
        article.className = "post-card dog-social-card js-searchable post-highlight";
        article.id = `post-${post.id}`;
        article.dataset.search = post.search_text || "";
        article.dataset.captionStatus = post.caption_status || "ready";

        const header = document.createElement("div");
        header.className = "post-header";
        const author = document.createElement("div");
        author.className = "post-author";
        author.appendChild(createPostAvatar(post));

        const authorCopy = document.createElement("div");
        const nameLink = document.createElement("a");
        nameLink.className = "profile-name-link";
        nameLink.href = `/profile/${encodeURIComponent(post.username || "")}`;
        const nameStrong = document.createElement("strong");
        nameStrong.textContent = post.pet_name || post.username || "";
        nameLink.appendChild(nameStrong);
        const meta = document.createElement("div");
        meta.className = "meta-line";
        meta.textContent = `${post.time_label || "방금 전"} · ${post.persona || ""}`;
        authorCopy.append(nameLink, meta);
        author.appendChild(authorCopy);

        const tools = document.createElement("div");
        tools.className = "post-header-tools";
        if (post.is_owner) {
            const edit = document.createElement("button");
            edit.type = "button";
            edit.className = "icon-button js-edit-post";
            edit.dataset.postId = post.id;
            edit.setAttribute("aria-label", "게시물 수정");
            edit.appendChild(createIcon("fa-regular fa-pen-to-square"));

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "icon-button danger-button js-delete-post";
            remove.dataset.postId = post.id;
            remove.setAttribute("aria-label", "게시물 삭제");
            remove.appendChild(createIcon("fa-regular fa-trash-can"));
            tools.append(edit, remove);
        }
        const species = document.createElement("span");
        species.className = "tag-pill";
        species.textContent = post.pet_species || "";
        tools.appendChild(species);
        header.append(author, tools);

        const imageButton = document.createElement("button");
        imageButton.type = "button";
        imageButton.className = "post-image-wrap js-open-post-detail";
        imageButton.dataset.postId = post.id;
        imageButton.setAttribute("aria-label", "게시물 상세 보기");
        const image = document.createElement("img");
        image.className = "post-image";
        image.src = post.image_url || "";
        image.alt = `${post.pet_name || "강아지"} 사진`;
        imageButton.appendChild(image);

        const actions = document.createElement("div");
        actions.className = "post-actions dog-social-actions";
        const like = document.createElement("button");
        like.type = "button";
        like.className = `dog-action-button js-like-button ${post.liked_by_viewer ? "is-liked" : ""}`;
        like.dataset.postId = post.id;
        like.dataset.liked = post.liked_by_viewer ? "true" : "false";
        like.setAttribute("aria-label", "좋아요");
        const likeCount = document.createElement("strong");
        likeCount.id = `like-count-${post.id}`;
        likeCount.dataset.likeCountFor = post.id;
        likeCount.textContent = post.likes || 0;
        like.append(createIcon("fa-solid fa-heart"), likeCount);

        const comment = document.createElement("button");
        comment.type = "button";
        comment.className = "dog-action-button js-comment-focus";
        comment.dataset.postId = post.id;
        comment.setAttribute("aria-label", "댓글");
        const commentCount = document.createElement("strong");
        commentCount.id = `comment-count-${post.id}`;
        commentCount.textContent = (post.comments || []).length;
        comment.append(createIcon("fa-regular fa-comment"), commentCount);

        const bookmark = document.createElement("button");
        bookmark.type = "button";
        bookmark.className = `icon-button save-button js-bookmark-button ${post.bookmarked_by_viewer ? "is-bookmarked" : ""}`;
        bookmark.dataset.postId = post.id;
        bookmark.dataset.bookmarked = post.bookmarked_by_viewer ? "true" : "false";
        bookmark.setAttribute("aria-label", "저장");
        bookmark.appendChild(createIcon("fa-regular fa-bookmark"));

        const detail = document.createElement("button");
        detail.type = "button";
        detail.className = "icon-button js-open-post-detail";
        detail.dataset.postId = post.id;
        detail.setAttribute("aria-label", "상세 보기");
        detail.appendChild(createIcon("fa-regular fa-window-maximize"));
        actions.append(like, comment, bookmark, detail);

        const copy = document.createElement("div");
        copy.className = "post-copy";
        const caption = document.createElement("p");
        caption.className = "caption";
        const captionName = document.createElement("strong");
        captionName.textContent = `${post.pet_name || ""}:`;
        const captionText = document.createElement("span");
        captionText.id = `caption-text-${post.id}`;
        captionText.className = post.caption_pending ? "caption-pending" : "";
        captionText.innerHTML = post.caption || "";
        caption.append(captionName, " ", captionText);
        copy.appendChild(caption);
        if (post.is_owner) {
            const editPanel = document.createElement("div");
            editPanel.className = "post-edit-panel";
            editPanel.id = `post-edit-${post.id}`;
            editPanel.hidden = true;
            const editInput = document.createElement("textarea");
            editInput.id = `post-edit-input-${post.id}`;
            editInput.rows = 4;
            editInput.maxLength = 700;
            editInput.value = post.caption_text || "";
            const editActions = document.createElement("div");
            editActions.className = "post-edit-actions";
            const cancel = document.createElement("button");
            cancel.type = "button";
            cancel.className = "ghost-button js-cancel-edit";
            cancel.dataset.postId = post.id;
            cancel.textContent = "취소";
            const save = document.createElement("button");
            save.type = "button";
            save.className = "primary-button js-save-post";
            save.dataset.postId = post.id;
            save.textContent = "저장";
            editActions.append(cancel, save);
            editPanel.append(editInput, editActions);
            copy.appendChild(editPanel);
        }

        const commentsBox = document.createElement("div");
        commentsBox.className = "comments-box";
        const list = document.createElement("div");
        list.id = `comment-list-${post.id}`;
        list.className = "comment-list";
        (post.comments || []).forEach((item) => list.appendChild(renderCommentItem(item, post.id)));
        const commentForm = document.createElement("div");
        commentForm.className = "comment-form";
        const input = document.createElement("input");
        input.type = "text";
        input.id = `comment-input-${post.id}`;
        input.placeholder = "댓글을 남겨보세요";
        const ai = document.createElement("button");
        ai.type = "button";
        ai.className = "ghost-button ai-comment-button js-ai-comment";
        ai.dataset.postId = post.id;
        ai.setAttribute("aria-label", "AI 댓글 만들기");
        const aiText = document.createElement("span");
        aiText.textContent = "AI";
        ai.append(createIcon("fa-solid fa-wand-magic-sparkles"), aiText);
        const submit = document.createElement("button");
        submit.type = "button";
        submit.className = "ghost-button js-comment-submit";
        submit.dataset.postId = post.id;
        submit.textContent = "게시";
        commentForm.append(input, ai, submit);
        commentsBox.append(list, commentForm);

        article.append(header, imageButton, actions, copy, commentsBox);
        window.setTimeout(() => article.classList.remove("post-highlight"), 2400);
        return article;
    }

    function prependPost(post) {
        const feed = document.querySelector(".feed-list");
        if (!feed || !post) return;
        feed.prepend(buildNewPostCard(post));
        if (post.caption_pending) pollPendingCaption(post.id);
    }

    function resetUploadForm() {
        const previewBox = document.getElementById("caption-preview-box");
        const previewInput = document.getElementById("caption-preview-input");
        const form = document.getElementById("uploadForm");
        if (form) form.reset();
        if (previewBox) previewBox.hidden = true;
        if (previewInput) previewInput.value = "";
        if (uploadPreviewImage) {
            uploadPreviewImage.removeAttribute("src");
            uploadPreviewImage.hidden = true;
        }
        if (fileName) fileName.textContent = "오늘 올릴 강아지 사진을 선택해 주세요";
    }

    function applyCaptionUpdate(post) {
        if (!post?.id) return;
        const status = post.caption_status || "ready";
        document.querySelectorAll(`#caption-text-${CSS.escape(String(post.id))}`).forEach((node) => {
            node.innerHTML = post.caption || "";
            node.classList.toggle("caption-pending", status === "pending");
        });
        document.querySelectorAll(`#post-${CSS.escape(String(post.id))}`).forEach((node) => {
            node.dataset.captionStatus = status;
        });
        document
            .querySelectorAll(`.js-profile-post-edit[data-post-id="${CSS.escape(String(post.id))}"], .js-open-post-detail[data-post-id="${CSS.escape(String(post.id))}"]`)
            .forEach((node) => {
                node.dataset.caption = post.caption_text || "";
            });
        if (activeDetailPostId === String(post.id)) {
            activeDetailPost = { ...(activeDetailPost || {}), ...post };
            renderPostDetail(activeDetailPost);
        }
    }

    function pollPendingCaption(postId) {
        const key = String(postId || "");
        if (!key || pendingCaptionPolls.has(key)) return;

        let attempts = 0;
        const poll = async () => {
            attempts += 1;
            try {
                const response = await fetch(`/api/posts/${encodeURIComponent(key)}`);
                const data = await response.json();
                if (response.ok && data.post) {
                    applyCaptionUpdate(data.post);
                    if (data.post.caption_status !== "pending") {
                        pendingCaptionPolls.delete(key);
                        showToast("AI 캡션이 완성됐어요.");
                        return;
                    }
                }
            } catch (error) {
                // Try again below unless the polling window has expired.
            }

            if (attempts < 30) {
                pendingCaptionPolls.set(key, window.setTimeout(poll, 2000));
            } else {
                pendingCaptionPolls.delete(key);
            }
        };

        pendingCaptionPolls.set(key, window.setTimeout(poll, 1500));
    }

    function initPendingCaptionPolling() {
        document.querySelectorAll(".post-card[data-caption-status='pending']").forEach((node) => {
            const match = String(node.id || "").match(/^post-(\d+)$/);
            if (match) pollPendingCaption(match[1]);
        });
    }

    function openPanel(panelName) {
        const panel = panels[panelName];
        if (!panel) return;
        panel.classList.add("open");
        panel.setAttribute("aria-hidden", "false");
    }

    function closePanel(panelName) {
        const panel = panels[panelName];
        if (!panel) return;
        panel.classList.remove("open");
        panel.setAttribute("aria-hidden", "true");
        if (panelName === "messages") stopMessageRefresh();
    }

    async function renderPersonaShareCanvas(card) {
        const profile = bootstrap.profile || {};
        const data = {
            petName: card.dataset.petName || profile.pet_name || "우리 강아지",
            persona: card.dataset.persona || profile.persona || "오늘의 주인공",
            summary: card.dataset.summary || profile.persona_summary || "귀여움 기록을 남기는 중이에요.",
            traits: (card.dataset.traits || "").split("·").map((item) => item.trim()).filter(Boolean),
            avatarUrl: card.dataset.avatarUrl || profile.display_avatar_url || profile.avatar_url || "",
            initial: card.dataset.initial || profile.initial || "멍",
        };

        if (document.fonts?.ready) {
            try {
                await document.fonts.ready;
            } catch (error) {
                // The canvas can still render with fallback fonts.
            }
        }

        const canvas = document.createElement("canvas");
        canvas.width = 1080;
        canvas.height = 1350;
        const context = canvas.getContext("2d");
        const background = context.createLinearGradient(0, 0, canvas.width, canvas.height);
        background.addColorStop(0, "#fff8ed");
        background.addColorStop(0.48, "#ffe0d4");
        background.addColorStop(1, "#cce7db");
        context.fillStyle = background;
        context.fillRect(0, 0, canvas.width, canvas.height);

        context.fillStyle = "rgba(245, 191, 79, 0.35)";
        context.beginPath();
        context.arc(160, 160, 170, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = "rgba(255, 255, 255, 0.48)";
        context.beginPath();
        context.arc(940, 250, 210, 0, Math.PI * 2);
        context.fill();

        drawRoundedRect(context, 72, 72, 936, 1206, 54, "rgba(255, 255, 255, 0.72)");
        context.strokeStyle = "rgba(117, 88, 70, 0.18)";
        context.lineWidth = 4;
        roundedRectPath(context, 96, 96, 888, 1158, 42);
        context.stroke();

        context.textAlign = "center";
        context.fillStyle = "#cf412d";
        context.font = "900 42px Jua, Pretendard, sans-serif";
        context.fillText("Zoo-In-Gong 성격 테스트", 540, 170);

        const image = await loadImageForCanvas(data.avatarUrl);
        if (image) {
            context.fillStyle = "rgba(255,255,255,0.88)";
            context.beginPath();
            context.arc(540, 355, 150, 0, Math.PI * 2);
            context.fill();
            drawCircularImage(context, image, 410, 225, 260);
        } else {
            context.fillStyle = "#fffaf4";
            context.beginPath();
            context.arc(540, 355, 130, 0, Math.PI * 2);
            context.fill();
            context.fillStyle = "#cf412d";
            context.font = "900 82px Jua, Pretendard, sans-serif";
            context.fillText(data.initial.slice(0, 2), 540, 385);
        }

        context.fillStyle = "#7a5847";
        context.font = "900 44px Jua, Pretendard, sans-serif";
        context.fillText(`${data.petName}는`, 540, 570);
        context.fillStyle = "#2d241e";
        context.font = "900 74px Jua, Pretendard, sans-serif";
        wrapCanvasText(context, data.persona, 540, 660, 820, 86, 2);

        context.fillStyle = "#5f4b40";
        context.font = "600 36px Pretendard, Jua, sans-serif";
        wrapCanvasText(context, data.summary, 540, 840, 800, 52, 4);

        const traits = data.traits.length ? data.traits.slice(0, 3) : ["오늘도 주인공", "귀여움 기록", "집사 심장 담당"];
        context.font = "900 30px Jua, Pretendard, sans-serif";
        const chips = traits.map((trait) => {
            const width = Math.min(260, Math.max(112, context.measureText(trait).width + 56));
            return {
                text: fitCanvasText(context, trait, width - 42),
                width,
            };
        });
        const chipGap = 16;
        const totalChipWidth = chips.reduce((sum, chip) => sum + chip.width, 0) + chipGap * Math.max(0, chips.length - 1);
        let chipX = 540 - totalChipWidth / 2;
        chips.forEach((chip) => {
            const width = chip.width;
            drawRoundedRect(context, chipX, 1042, width, 58, 29, "rgba(255,255,255,0.76)");
            context.fillStyle = "#684536";
            context.fillText(chip.text, chipX + width / 2, 1080);
            chipX += width + chipGap;
        });

        context.fillStyle = "#cf412d";
        context.font = "900 34px Jua, Pretendard, sans-serif";
        context.fillText("#강아지성격테스트 #오늘도주인공", 540, 1195);
        context.fillStyle = "#7a685d";
        context.font = "700 28px Pretendard, Jua, sans-serif";
        context.fillText("zoo-in-gong.local", 540, 1240);
        return canvas;
    }

    function personaShareText(card) {
        const petName = card.dataset.petName || bootstrap.profile?.pet_name || "우리 강아지";
        const persona = card.dataset.persona || bootstrap.profile?.persona || "오늘의 주인공";
        const summary = card.dataset.summary || bootstrap.profile?.persona_summary || "";
        return `${petName} 성격 테스트 결과는 ${persona}!\n${summary}\n#ZooInGong #강아지성격테스트 #오늘도주인공`;
    }

    async function copyText(text) {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    }

    function initPersonaShareCard() {
        const card = document.getElementById("persona-share-section");
        if (!card) return;

        document.querySelectorAll(".js-download-persona-card").forEach((button) => {
            button.addEventListener("click", async () => {
                button.disabled = true;
                try {
                    const canvas = await renderPersonaShareCanvas(card);
                    const petName = (card.dataset.petName || "dog").replace(/[^\w가-힣-]+/g, "_");
                    downloadCanvas(canvas, `${petName}_성격테스트.png`);
                    showToast("공유 카드를 저장했어요.");
                } catch (error) {
                    showToast("카드 저장에 실패했어요.");
                } finally {
                    button.disabled = false;
                }
            });
        });

        document.querySelectorAll(".js-copy-persona-share").forEach((button) => {
            button.addEventListener("click", async () => {
                try {
                    await copyText(personaShareText(card));
                    showToast("공유 문구를 복사했어요.");
                } catch (error) {
                    showToast("문구 복사에 실패했어요.");
                }
            });
        });
    }

    function studioDrawCoverImage(context, image, x, y, width, height) {
        const scale = Math.max(width / image.width, height / image.height);
        const drawWidth = image.width * scale;
        const drawHeight = image.height * scale;
        context.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
    }

    function studioDrawHeart(context, x, y, size, color) {
        context.save();
        context.translate(x, y);
        context.scale(size / 100, size / 100);
        context.beginPath();
        context.moveTo(50, 86);
        context.bezierCurveTo(20, 64, 6, 48, 10, 28);
        context.bezierCurveTo(14, 8, 38, 4, 50, 24);
        context.bezierCurveTo(62, 4, 86, 8, 90, 28);
        context.bezierCurveTo(94, 48, 80, 64, 50, 86);
        context.fillStyle = color;
        context.fill();
        context.restore();
    }

    function studioDrawStar(context, cx, cy, outer, inner, color) {
        context.beginPath();
        for (let i = 0; i < 10; i += 1) {
            const angle = -Math.PI / 2 + (i * Math.PI) / 5;
            const radius = i % 2 === 0 ? outer : inner;
            const x = cx + Math.cos(angle) * radius;
            const y = cy + Math.sin(angle) * radius;
            if (i === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
        }
        context.closePath();
        context.fillStyle = color;
        context.fill();
    }

    function studioDrawSticker(context, type, x = 560, y = 150, scale = 1, rotation = 0, assets = {}) {
        context.save();
        context.translate(x, y);
        context.rotate(rotation);
        context.scale(scale, scale);
        context.translate(-560, -150);
        context.lineWidth = 8;
        context.lineCap = "round";
        context.lineJoin = "round";
        if (type.startsWith("image")) {
            const image = assets.imageStickers?.[type];
            if (image && image.complete && image.naturalWidth > 0) {
                const size = assets.stickerSize?.(type, 1) || { width: 260, height: 236 };
                const maxWidth = size.width;
                const maxHeight = size.height;
                const ratio = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
                const drawWidth = image.naturalWidth * ratio;
                const drawHeight = image.naturalHeight * ratio;
                context.drawImage(image, 560 - drawWidth / 2, 150 - drawHeight / 2, drawWidth, drawHeight);
            }
        } else if (type === "speechbubble") {
            const image = assets.speechBubbleImage;
            if (image && image.complete && image.naturalWidth > 0) {
                context.drawImage(image, 395, 40, 330, 233);
            } else {
                drawRoundedRect(context, 404, 76, 270, 156, 78, "#ffffff");
                context.strokeStyle = "#111111";
                context.lineWidth = 8;
                context.stroke();
                context.beginPath();
                context.moveTo(642, 86);
                context.lineTo(700, 24);
                context.lineTo(668, 118);
                context.stroke();
            }

            context.fillStyle = "#2d241e";
            const bubbleTextSize = Math.max(18, Math.min(48, Number(assets.bubbleTextSize) || 28));
            const bubbleLineHeight = bubbleTextSize * 1.22;
            context.font = `900 ${bubbleTextSize}px Jua, Pretendard, sans-serif`;
            context.textAlign = "center";
            context.textBaseline = "middle";
            const bubbleText = String(assets.bubbleText || "").trim() || "여기에 입력";
            const lines = [];
            let line = "";
            for (const char of bubbleText) {
                const nextLine = `${line}${char}`;
                if (context.measureText(nextLine).width <= 216) {
                    line = nextLine;
                } else {
                    if (line) lines.push(line);
                    line = char;
                }
            }
            if (line) lines.push(line);
            const outputLines = lines.slice(0, 3);
            if (lines.length > 3) {
                outputLines[2] = fitCanvasText(context, outputLines[2], 206);
            }
            const startY = 159 - ((outputLines.length - 1) * bubbleLineHeight) / 2;
            outputLines.forEach((lineText, index) => {
                context.fillText(lineText, 552, startY + index * bubbleLineHeight);
            });
            context.textBaseline = "alphabetic";
        } else if (type === "crown") {
            context.fillStyle = "#f5bf4f";
            context.strokeStyle = "#7a4f18";
            context.beginPath();
            context.moveTo(472, 170);
            context.lineTo(504, 98);
            context.lineTo(548, 158);
            context.lineTo(592, 98);
            context.lineTo(624, 170);
            context.closePath();
            context.fill();
            context.stroke();
            drawRoundedRect(context, 478, 170, 140, 38, 14, "#f5bf4f");
            context.strokeRect(486, 176, 124, 26);
        } else if (type === "gem") {
            context.fillStyle = "#d96bff";
            context.strokeStyle = "#7a3fac";
            context.beginPath();
            context.moveTo(560, 72);
            context.lineTo(640, 130);
            context.lineTo(586, 226);
            context.lineTo(500, 226);
            context.lineTo(462, 124);
            context.closePath();
            context.fill();
            context.stroke();
            context.strokeStyle = "rgba(255,255,255,0.72)";
            context.lineWidth = 6;
            context.beginPath();
            context.moveTo(500, 126);
            context.lineTo(636, 130);
            context.moveTo(560, 72);
            context.lineTo(586, 226);
            context.stroke();
        } else if (type === "dog") {
            context.fillStyle = "#d8aa73";
            context.strokeStyle = "#2d241e";
            context.lineWidth = 7;
            context.beginPath();
            context.ellipse(560, 148, 70, 58, 0, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#8f643d";
            context.beginPath();
            context.ellipse(494, 146, 24, 42, -0.36, 0, Math.PI * 2);
            context.ellipse(626, 146, 24, 42, 0.36, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#2d241e";
            context.beginPath();
            context.arc(538, 146, 9, 0, Math.PI * 2);
            context.arc(582, 146, 9, 0, Math.PI * 2);
            context.fill();
            context.beginPath();
            context.arc(560, 170, 13, 0, Math.PI * 2);
            context.fill();
            context.strokeStyle = "#2d241e";
            context.lineWidth = 8;
            roundedRectPath(context, 518, 118, 44, 30, 13);
            context.stroke();
            roundedRectPath(context, 574, 118, 44, 30, 13);
            context.stroke();
            context.beginPath();
            context.moveTo(562, 134);
            context.lineTo(574, 134);
            context.stroke();
        } else if (type === "snack") {
            context.fillStyle = "#8f4c2c";
            context.strokeStyle = "#4f2a1c";
            context.lineWidth = 8;
            context.beginPath();
            context.ellipse(574, 148, 52, 74, 0.36, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#6fc66d";
            context.beginPath();
            context.moveTo(612, 96);
            context.quadraticCurveTo(664, 88, 650, 138);
            context.quadraticCurveTo(620, 132, 612, 96);
            context.fill();
            context.stroke();
            context.fillStyle = "#f5bf4f";
            context.beginPath();
            context.arc(540, 124, 7, 0, Math.PI * 2);
            context.arc(596, 162, 7, 0, Math.PI * 2);
            context.arc(556, 194, 6, 0, Math.PI * 2);
            context.fill();
        } else if (type === "hundred") {
            context.fillStyle = "#ef4e38";
            context.font = "900 70px Jua, Pretendard, sans-serif";
            context.textAlign = "center";
            context.fillText("1000000", 560, 156);
            context.strokeStyle = "#ef4e38";
            context.lineWidth = 9;
            context.beginPath();
            context.moveTo(448, 186);
            context.quadraticCurveTo(540, 202, 672, 176);
            context.stroke();
        } else if (type === "heart") {
            studioDrawHeart(context, 512, 86, 142, "#9b5cff");
            context.fillStyle = "#2d241e";
            context.beginPath();
            context.arc(548, 142, 6, 0, Math.PI * 2);
            context.arc(590, 142, 6, 0, Math.PI * 2);
            context.fill();
            context.strokeStyle = "#2d241e";
            context.lineWidth = 5;
            context.beginPath();
            context.arc(568, 162, 18, 0.2, Math.PI - 0.2);
            context.stroke();
        } else if (type === "rainbow") {
            const bands = ["#f05d68", "#f5bf4f", "#7bd35d", "#65dcff", "#9b5cff"];
            context.lineCap = "round";
            bands.forEach((color, index) => {
                context.strokeStyle = color;
                context.lineWidth = 12;
                context.beginPath();
                context.arc(560, 186, 76 - index * 12, Math.PI, Math.PI * 2);
                context.stroke();
            });
            context.fillStyle = "#ffffff";
            context.strokeStyle = "#e5dfd7";
            drawRoundedRect(context, 462, 172, 60, 36, 20, "#ffffff");
            context.stroke();
            drawRoundedRect(context, 598, 172, 60, 36, 20, "#ffffff");
            context.stroke();
        } else if (type === "donut") {
            context.fillStyle = "#f05dce";
            context.strokeStyle = "#f5bf4f";
            context.lineWidth = 14;
            context.beginPath();
            context.arc(560, 150, 66, 0, Math.PI * 2);
            context.stroke();
            context.fillStyle = "#ff7dd8";
            context.beginPath();
            context.arc(560, 150, 52, 0, Math.PI * 2);
            context.fill();
            context.fillStyle = "rgba(255,255,255,0.92)";
            context.beginPath();
            context.arc(560, 150, 22, 0, Math.PI * 2);
            context.fill();
            ["#ffffff", "#f5bf4f", "#65dcff", "#7bd35d"].forEach((color, index) => {
                context.strokeStyle = color;
                context.lineWidth = 5;
                context.beginPath();
                context.moveTo(528 + index * 18, 118 + (index % 2) * 42);
                context.lineTo(548 + index * 18, 126 + (index % 2) * 32);
                context.stroke();
            });
        } else if (type === "glasses") {
            context.strokeStyle = "#2d241e";
            context.lineWidth = 10;
            roundedRectPath(context, 486, 126, 64, 48, 20);
            context.stroke();
            roundedRectPath(context, 584, 126, 64, 48, 20);
            context.stroke();
            context.beginPath();
            context.moveTo(550, 150);
            context.lineTo(584, 150);
            context.stroke();
        } else if (type === "wizard") {
            context.fillStyle = "#cc55d8";
            context.strokeStyle = "#773680";
            context.lineWidth = 8;
            context.beginPath();
            context.moveTo(560, 64);
            context.lineTo(650, 222);
            context.lineTo(470, 222);
            context.closePath();
            context.fill();
            context.stroke();
            context.fillStyle = "#ffffff";
            for (const star of [[540, 124], [588, 158], [566, 198]]) {
                studioDrawStar(context, star[0], star[1], 10, 4, "#ffffff");
            }
            context.strokeStyle = "#7bd35d";
            context.lineWidth = 10;
            context.beginPath();
            context.moveTo(462, 226);
            context.quadraticCurveTo(560, 246, 660, 222);
            context.stroke();
        } else if (type === "alien") {
            context.fillStyle = "#c7eef1";
            context.strokeStyle = "#2d241e";
            context.lineWidth = 7;
            context.beginPath();
            context.ellipse(560, 150, 76, 58, 0, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#9fd4d8";
            context.beginPath();
            context.moveTo(492, 116);
            context.lineTo(442, 82);
            context.lineTo(468, 144);
            context.fill();
            context.stroke();
            context.fillStyle = "#2d241e";
            context.beginPath();
            context.ellipse(532, 146, 10, 16, -0.36, 0, Math.PI * 2);
            context.ellipse(588, 146, 10, 16, 0.36, 0, Math.PI * 2);
            context.fill();
            context.strokeStyle = "#2d241e";
            context.lineWidth = 5;
            context.beginPath();
            context.arc(560, 174, 22, 0.2, Math.PI - 0.2);
            context.stroke();
        } else if (type === "bubble") {
            drawRoundedRect(context, 478, 98, 168, 88, 34, "#ffffff");
            context.strokeStyle = "#7a685d";
            context.stroke();
            context.fillStyle = "#ffffff";
            context.beginPath();
            context.moveTo(526, 178);
            context.lineTo(500, 222);
            context.lineTo(568, 184);
            context.fill();
            context.stroke();
        } else if (type === "burger") {
            context.strokeStyle = "#4d2b1c";
            context.lineWidth = 8;
            drawRoundedRect(context, 478, 102, 164, 52, 26, "#e2a14f");
            context.stroke();
            context.fillStyle = "#ffffff";
            context.beginPath();
            context.arc(520, 118, 4, 0, Math.PI * 2);
            context.arc(560, 112, 4, 0, Math.PI * 2);
            context.arc(606, 122, 4, 0, Math.PI * 2);
            context.fill();
            drawRoundedRect(context, 470, 146, 180, 34, 12, "#7bd35d");
            drawRoundedRect(context, 478, 170, 164, 42, 14, "#7b3f24");
            drawRoundedRect(context, 486, 202, 148, 34, 16, "#f5bf4f");
            context.strokeStyle = "#4d2b1c";
            roundedRectPath(context, 478, 102, 164, 134, 30);
            context.stroke();
        } else if (type === "lips") {
            context.fillStyle = "#ff536a";
            context.strokeStyle = "#8b1d2e";
            context.lineWidth = 7;
            context.beginPath();
            context.moveTo(454, 154);
            context.bezierCurveTo(500, 88, 538, 128, 560, 140);
            context.bezierCurveTo(590, 104, 628, 100, 666, 154);
            context.bezierCurveTo(620, 206, 502, 206, 454, 154);
            context.fill();
            context.stroke();
            context.strokeStyle = "rgba(255,255,255,0.8)";
            context.lineWidth = 5;
            context.beginPath();
            context.moveTo(498, 152);
            context.quadraticCurveTo(560, 172, 626, 152);
            context.stroke();
        } else if (type === "pixelheart") {
            const blocks = [
                [0, 1], [0, 2], [1, 0], [1, 1], [1, 2], [1, 3],
                [2, 0], [2, 1], [2, 2], [2, 3], [3, 1], [3, 2],
                [4, 2],
            ];
            context.fillStyle = "#63caff";
            context.strokeStyle = "#4d8fe8";
            context.lineWidth = 4;
            blocks.forEach(([row, col]) => {
                context.fillRect(500 + col * 30, 86 + row * 30, 30, 30);
                context.strokeRect(500 + col * 30, 86 + row * 30, 30, 30);
            });
        } else if (type === "shades") {
            context.strokeStyle = "#5b45df";
            context.lineWidth = 8;
            drawRoundedRect(context, 464, 124, 72, 50, 16, "#95efff");
            context.stroke();
            drawRoundedRect(context, 584, 124, 72, 50, 16, "#b772ff");
            context.stroke();
            context.beginPath();
            context.moveTo(536, 148);
            context.lineTo(584, 148);
            context.stroke();
            context.strokeStyle = "rgba(255,255,255,0.82)";
            context.lineWidth = 5;
            context.beginPath();
            context.moveTo(482, 136);
            context.lineTo(518, 130);
            context.moveTo(604, 136);
            context.lineTo(640, 130);
            context.stroke();
        }
        context.restore();
    }

    function initStudioMaker() {
        const canvas = document.getElementById("studio-canvas");
        if (!canvas) return;

        const context = canvas.getContext("2d");
        const backgroundButtons = document.querySelectorAll("[data-studio-background]");
        const textPresetButtons = document.querySelectorAll("[data-studio-text]");
        const colorButtons = document.querySelectorAll("[data-studio-color]");
        const stickerButtons = document.querySelectorAll("[data-studio-sticker]");
        const downloadButtons = document.querySelectorAll(".js-studio-download");
        const textInput = document.getElementById("studio-text-input");
        const bubbleTextInput = document.getElementById("studio-bubble-text-input");
        const bubbleSizeInput = document.getElementById("studio-bubble-size-input");
        const fileInput = document.getElementById("studio-file-input");
        const speechBubbleImage = document.getElementById("studio-speech-bubble-asset");
        const imageStickers = {
            imagecrown: document.getElementById("studio-crown-sticker-asset"),
            imageheart: document.getElementById("studio-heart-sticker-asset"),
            imageflower: document.getElementById("studio-flower-sticker-asset"),
            imageglasses: document.getElementById("studio-glasses-sticker-asset"),
            imagestar: document.getElementById("studio-star-sticker-asset"),
            imagebone: document.getElementById("studio-bone-sticker-asset"),
        };
        let stickerCounter = 0;
        const state = {
            image: null,
            background: "cream",
            text: "나 불렀개?",
            showText: true,
            textColor: "#ffffff",
            textX: 360,
            textY: 520,
            textSize: 58,
            textRotation: 0,
            stickers: [],
            selectedElement: "text",
            selectedStickerId: null,
        };
        const backgrounds = {
            cream: ["#fff5df", "#ffd5c7"],
            mint: ["#e2f6e8", "#b5ddcf"],
            sky: ["#e4f2ff", "#acd6ff"],
            pink: ["#ffe7ef", "#ffb7cd"],
            lime: ["#f3ffd8", "#d9eaa2"],
            night: ["#4b587c", "#20263a"],
        };
        const layout = {
            text: null,
            textHandle: null,
            textRotateHandle: null,
            textDeleteHandle: null,
            stickers: new Map(),
        };

        function clampStudioValue(value, min, max) {
            return Math.max(min, Math.min(max, value));
        }

        function stickerSize(type, scale = 1) {
            if (type === "speechbubble") return { width: 330 * scale, height: 233 * scale };
            if (type === "imageglasses") return { width: 330 * scale, height: 140 * scale };
            if (type === "imagebone") return { width: 330 * scale, height: 186 * scale };
            if (type.startsWith("image")) return { width: 260 * scale, height: 250 * scale };
            return { width: 224 * scale, height: 224 * scale };
        }

        function makeSticker(type, options = {}) {
            const offset = (stickerCounter % 5) * 28;
            stickerCounter += 1;
            return {
                id: `sticker-${Date.now()}-${stickerCounter}`,
                type,
                x: clampStudioValue(options.x ?? 560 - offset, 140, 610),
                y: clampStudioValue(options.y ?? 150 + offset, 120, 610),
                scale: options.scale ?? 1,
                rotation: options.rotation ?? 0,
                bubbleText: bubbleTextInput?.value || "여기에 입력",
                bubbleTextSize: clampStudioValue(Number(bubbleSizeInput?.value) || 28, 18, 48),
            };
        }

        function selectedSticker() {
            return state.stickers.find((sticker) => sticker.id === state.selectedStickerId) || null;
        }

        function updateStickerButtons() {
            const sticker = selectedSticker();
            stickerButtons.forEach((button) => {
                button.classList.toggle("is-active", Boolean(sticker && button.dataset.studioSticker === sticker.type));
            });
        }

        function addSticker(type) {
            const sticker = makeSticker(type || "imagecrown");
            state.stickers.push(sticker);
            state.selectedElement = "sticker";
            state.selectedStickerId = sticker.id;
            updateStickerButtons();
            renderStudioCanvas();
        }

        function rectCenter(rect) {
            return {
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
            };
        }

        function rotatePoint(x, y, centerX, centerY, rotation) {
            const cos = Math.cos(rotation);
            const sin = Math.sin(rotation);
            const dx = x - centerX;
            const dy = y - centerY;
            return {
                x: centerX + dx * cos - dy * sin,
                y: centerY + dx * sin + dy * cos,
            };
        }

        function resizeHandleRect(rect) {
            if (!rect) return null;
            const size = 30;
            const center = rectCenter(rect);
            const handleCenter = rotatePoint(rect.x + rect.width, rect.y + rect.height, center.x, center.y, rect.rotation || 0);
            return { x: handleCenter.x - size / 2, y: handleCenter.y - size / 2, width: size, height: size };
        }

        function rotateHandleRect(rect) {
            if (!rect) return null;
            const size = 30;
            const center = rectCenter(rect);
            let handleCenter = rotatePoint(rect.x + rect.width / 2, rect.y - 58, center.x, center.y, rect.rotation || 0);
            if (handleCenter.y < size || handleCenter.x < size || handleCenter.x > canvas.width - size) {
                handleCenter = rotatePoint(rect.x + rect.width / 2, rect.y + rect.height + 58, center.x, center.y, rect.rotation || 0);
            }
            return { x: handleCenter.x - size / 2, y: handleCenter.y - size / 2, width: size, height: size };
        }

        function deleteHandleRect(rect) {
            if (!rect) return null;
            const size = 32;
            const center = rectCenter(rect);
            const handleCenter = rotatePoint(rect.x, rect.y, center.x, center.y, rect.rotation || 0);
            return { x: handleCenter.x - size / 2, y: handleCenter.y - size / 2, width: size, height: size };
        }

        function pointHitsRotatedRect(point, rect) {
            if (!rect) return false;
            const center = rectCenter(rect);
            const localPoint = rotatePoint(point.x, point.y, center.x, center.y, -(rect.rotation || 0));
            return (
                localPoint.x >= rect.x &&
                localPoint.x <= rect.x + rect.width &&
                localPoint.y >= rect.y &&
                localPoint.y <= rect.y + rect.height
            );
        }

        function pointHitsRect(point, rect) {
            if (!rect) return false;
            return point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height;
        }

        function drawStudioSelection(rect) {
            if (!rect) return;
            const handle = resizeHandleRect(rect);
            const rotateHandle = rotateHandleRect(rect);
            const deleteHandle = deleteHandleRect(rect);
            const center = rectCenter(rect);
            context.save();
            context.translate(center.x, center.y);
            context.rotate(rect.rotation || 0);
            context.strokeStyle = "rgba(255,255,255,0.96)";
            context.lineWidth = 4;
            context.setLineDash([10, 8]);
            context.strokeRect(-rect.width / 2 - 8, -rect.height / 2 - 8, rect.width + 16, rect.height + 16);
            context.setLineDash([]);
            context.restore();

            context.save();
            context.strokeStyle = "rgba(255,255,255,0.96)";
            context.lineWidth = 4;
            context.beginPath();
            context.moveTo(center.x, center.y);
            context.lineTo(rotateHandle.x + rotateHandle.width / 2, rotateHandle.y + rotateHandle.height / 2);
            context.stroke();
            context.fillStyle = "#f05d44";
            context.strokeStyle = "#ffffff";
            context.lineWidth = 5;
            roundedRectPath(context, handle.x, handle.y, handle.width, handle.height, 10);
            context.fill();
            context.stroke();
            context.fillStyle = "#7b61ff";
            context.beginPath();
            context.arc(rotateHandle.x + rotateHandle.width / 2, rotateHandle.y + rotateHandle.height / 2, rotateHandle.width / 2, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#ef4e38";
            context.beginPath();
            context.arc(deleteHandle.x + deleteHandle.width / 2, deleteHandle.y + deleteHandle.height / 2, deleteHandle.width / 2, 0, Math.PI * 2);
            context.fill();
            context.stroke();
            context.fillStyle = "#ffffff";
            context.font = "900 18px Jua, Pretendard, sans-serif";
            context.textAlign = "center";
            context.textBaseline = "middle";
            context.fillText("↻", rotateHandle.x + rotateHandle.width / 2, rotateHandle.y + rotateHandle.height / 2 + 1);
            context.fillText("×", deleteHandle.x + deleteHandle.width / 2, deleteHandle.y + deleteHandle.height / 2 + 1);
            context.textBaseline = "alphabetic";
            context.restore();
        }

        function renderStudioCanvas(options = {}) {
            const showControls = options.showControls !== false;
            if (state.image) {
                studioDrawCoverImage(context, state.image, 0, 0, canvas.width, canvas.height);
            } else {
                const [a, b] = backgrounds[state.background] || backgrounds.cream;
                const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height);
                gradient.addColorStop(0, a);
                gradient.addColorStop(1, b);
                context.fillStyle = gradient;
                context.fillRect(0, 0, canvas.width, canvas.height);
                context.fillStyle = "rgba(255,255,255,0.26)";
                context.beginPath();
                context.arc(90, 84, 116, 0, Math.PI * 2);
                context.arc(638, 112, 92, 0, Math.PI * 2);
                context.fill();
                drawRoundedRect(context, 130, 96, 460, 460, 58, "rgba(255,255,255,0.82)");
                context.fillStyle = "#cf412d";
                context.font = "900 54px Jua, Pretendard, sans-serif";
                context.textAlign = "center";
                context.fillText("사진", 360, 336);
            }

            layout.stickers.clear();
            state.stickers.forEach((sticker) => {
                const bounds = stickerSize(sticker.type, sticker.scale);
                const rect = {
                    x: sticker.x - bounds.width / 2,
                    y: sticker.y - bounds.height / 2,
                    width: bounds.width,
                    height: bounds.height,
                    rotation: sticker.rotation,
                };
                rect.resizeHandle = resizeHandleRect(rect);
                rect.rotateHandle = rotateHandleRect(rect);
                rect.deleteHandle = deleteHandleRect(rect);
                layout.stickers.set(sticker.id, rect);
                studioDrawSticker(context, sticker.type, sticker.x, sticker.y, sticker.scale, sticker.rotation, {
                    speechBubbleImage,
                    imageStickers,
                    stickerSize,
                    bubbleText: sticker.bubbleText,
                    bubbleTextSize: sticker.bubbleTextSize,
                });
            });

            if (state.showText) {
                context.font = `900 ${state.textSize}px Jua, Pretendard, sans-serif`;
                context.textAlign = "center";
                context.textBaseline = "middle";
                const maxTextWidth = canvas.width - 52;
                const memeText = fitCanvasText(context, state.text || " ", maxTextWidth - state.textSize);
                const textWidth = clampStudioValue(context.measureText(memeText).width + state.textSize * 0.86, 96, maxTextWidth);
                const labelHeight = clampStudioValue(state.textSize * 1.34, 44, 160);
                const labelX = Math.max(26, Math.min(canvas.width - textWidth - 26, state.textX - textWidth / 2));
                const labelY = Math.max(26, Math.min(canvas.height - labelHeight - 46, state.textY - labelHeight / 2));
                layout.text = { x: labelX, y: labelY, width: textWidth, height: labelHeight, rotation: state.textRotation };
                layout.textHandle = resizeHandleRect(layout.text);
                layout.textRotateHandle = rotateHandleRect(layout.text);
                layout.textDeleteHandle = deleteHandleRect(layout.text);
                layout.text.resizeHandle = layout.textHandle;
                layout.text.rotateHandle = layout.textRotateHandle;
                layout.text.deleteHandle = layout.textDeleteHandle;
                const labelCenter = rectCenter(layout.text);
                context.save();
                context.translate(labelCenter.x, labelCenter.y);
                context.rotate(state.textRotation);
                drawRoundedRect(context, -textWidth / 2, -labelHeight / 2, textWidth, labelHeight, 8, "rgba(0,0,0,0.72)");
                context.fillStyle = state.textColor;
                context.fillText(memeText, 0, 3);
                context.restore();
                context.textBaseline = "alphabetic";
            } else {
                layout.text = null;
                layout.textHandle = null;
                layout.textRotateHandle = null;
                layout.textDeleteHandle = null;
            }

            context.fillStyle = state.background === "night" ? "rgba(255,255,255,0.82)" : "rgba(104,69,54,0.78)";
            context.font = "900 24px Jua, Pretendard, sans-serif";
            context.fillText("Zoo-In-Gong", 360, 704);

            if (showControls && state.selectedElement === "text" && state.showText) {
                drawStudioSelection(layout.text);
            } else if (showControls && state.selectedElement === "sticker") {
                drawStudioSelection(layout.stickers.get(state.selectedStickerId));
            }
        }

        function canvasPointFromEvent(event) {
            const rect = canvas.getBoundingClientRect();
            return {
                x: ((event.clientX - rect.left) / rect.width) * canvas.width,
                y: ((event.clientY - rect.top) / rect.height) * canvas.height,
            };
        }

        function deleteSelectedSticker() {
            state.stickers = state.stickers.filter((sticker) => sticker.id !== state.selectedStickerId);
            const nextSticker = state.stickers[state.stickers.length - 1] || null;
            state.selectedStickerId = nextSticker?.id || null;
            state.selectedElement = nextSticker ? "sticker" : state.showText ? "text" : "sticker";
            updateStickerButtons();
            renderStudioCanvas();
        }

        let activeDrag = null;

        canvas.addEventListener("pointerdown", (event) => {
            const point = canvasPointFromEvent(event);
            if (state.selectedElement === "text" && state.showText && pointHitsRect(point, layout.textDeleteHandle)) {
                state.showText = false;
                state.selectedElement = state.stickers.length ? "sticker" : "text";
                state.selectedStickerId = state.stickers[state.stickers.length - 1]?.id || null;
                textPresetButtons.forEach((preset) => preset.classList.remove("is-active"));
                renderStudioCanvas();
                return;
            }
            if (state.selectedElement === "text" && state.showText && pointHitsRect(point, layout.textRotateHandle)) {
                const center = rectCenter(layout.text);
                activeDrag = {
                    mode: "rotate",
                    target: "text",
                    centerX: center.x,
                    centerY: center.y,
                    startAngle: Math.atan2(point.y - center.y, point.x - center.x),
                    startRotation: state.textRotation,
                };
            } else if (state.selectedElement === "text" && state.showText && pointHitsRect(point, layout.textHandle)) {
                activeDrag = {
                    mode: "resize",
                    target: "text",
                    startX: point.x,
                    startY: point.y,
                    startTextSize: state.textSize,
                };
            }
            if (state.selectedElement === "sticker") {
                const selectedRect = layout.stickers.get(state.selectedStickerId);
                if (pointHitsRect(point, selectedRect?.deleteHandle)) {
                    deleteSelectedSticker();
                    return;
                }
                if (selectedRect && pointHitsRect(point, selectedRect.rotateHandle)) {
                    const center = rectCenter(selectedRect);
                    const sticker = selectedSticker();
                    activeDrag = {
                        mode: "rotate",
                        target: "sticker",
                        stickerId: sticker.id,
                        centerX: center.x,
                        centerY: center.y,
                        startAngle: Math.atan2(point.y - center.y, point.x - center.x),
                        startRotation: sticker.rotation,
                    };
                } else if (selectedRect && pointHitsRect(point, selectedRect.resizeHandle)) {
                    const sticker = selectedSticker();
                    activeDrag = { mode: "resize", target: "sticker", stickerId: sticker.id, startX: point.x, startY: point.y, startStickerScale: sticker.scale };
                }
            }
            if (!activeDrag) {
                for (let index = state.stickers.length - 1; index >= 0; index -= 1) {
                    const sticker = state.stickers[index];
                    const rect = layout.stickers.get(sticker.id);
                    if (pointHitsRotatedRect(point, rect)) {
                        state.selectedElement = "sticker";
                        state.selectedStickerId = sticker.id;
                        activeDrag = { mode: "move", target: "sticker", stickerId: sticker.id, offsetX: point.x - sticker.x, offsetY: point.y - sticker.y };
                        updateStickerButtons();
                        break;
                    }
                }
            }
            if (!activeDrag && state.showText && pointHitsRotatedRect(point, layout.text)) {
                state.selectedElement = "text";
                state.selectedStickerId = null;
                updateStickerButtons();
                const center = rectCenter(layout.text);
                activeDrag = { mode: "move", target: "text", offsetX: point.x - center.x, offsetY: point.y - center.y };
            }
            if (!activeDrag) return;
            event.preventDefault();
            canvas.classList.add("is-dragging");
            renderStudioCanvas();
            canvas.setPointerCapture?.(event.pointerId);
        });

        canvas.addEventListener("pointermove", (event) => {
            const point = canvasPointFromEvent(event);
            if (!activeDrag) {
                const selectedRect = state.selectedElement === "sticker" ? layout.stickers.get(state.selectedStickerId) : layout.text;
                if (pointHitsRect(point, selectedRect?.deleteHandle)) {
                    canvas.style.cursor = "pointer";
                } else if (pointHitsRect(point, selectedRect?.rotateHandle || layout.textRotateHandle)) {
                    canvas.style.cursor = "grab";
                } else if (pointHitsRect(point, selectedRect?.resizeHandle || layout.textHandle)) {
                    canvas.style.cursor = "nwse-resize";
                } else if (
                    (state.showText && pointHitsRotatedRect(point, layout.text)) ||
                    state.stickers.some((sticker) => pointHitsRotatedRect(point, layout.stickers.get(sticker.id)))
                ) {
                    canvas.style.cursor = "move";
                } else {
                    canvas.style.cursor = "";
                }
                return;
            }

            event.preventDefault();
            if (activeDrag.target === "sticker") {
                const sticker = state.stickers.find((item) => item.id === activeDrag.stickerId);
                if (!sticker) return;
                if (activeDrag.mode === "rotate") {
                    const angle = Math.atan2(point.y - activeDrag.centerY, point.x - activeDrag.centerX);
                    sticker.rotation = activeDrag.startRotation + angle - activeDrag.startAngle;
                } else if (activeDrag.mode === "resize") {
                    const delta = Math.max(point.x - activeDrag.startX, point.y - activeDrag.startY);
                    sticker.scale = clampStudioValue(activeDrag.startStickerScale + delta / 130, 0.45, 2.35);
                    const bounds = stickerSize(sticker.type, sticker.scale);
                    sticker.x = clampStudioValue(sticker.x, bounds.width / 2, canvas.width - bounds.width / 2);
                    sticker.y = clampStudioValue(sticker.y, bounds.height / 2, canvas.height - bounds.height / 2);
                } else {
                    const bounds = stickerSize(sticker.type, sticker.scale);
                    sticker.x = clampStudioValue(point.x - activeDrag.offsetX, bounds.width / 2, canvas.width - bounds.width / 2);
                    sticker.y = clampStudioValue(point.y - activeDrag.offsetY, bounds.height / 2, canvas.height - bounds.height / 2);
                }
            } else if (activeDrag.mode === "rotate") {
                const angle = Math.atan2(point.y - activeDrag.centerY, point.x - activeDrag.centerX);
                state.textRotation = activeDrag.startRotation + angle - activeDrag.startAngle;
            } else if (activeDrag.mode === "resize") {
                const delta = Math.max(point.x - activeDrag.startX, point.y - activeDrag.startY);
                state.textSize = clampStudioValue(activeDrag.startTextSize + delta * 0.36, 30, 112);
            } else {
                state.textX = clampStudioValue(point.x - activeDrag.offsetX, 90, 630);
                state.textY = clampStudioValue(point.y - activeDrag.offsetY, 150, 650);
            }
            renderStudioCanvas();
        });

        function endCanvasDrag(event) {
            if (!activeDrag) return;
            activeDrag = null;
            canvas.classList.remove("is-dragging");
            canvas.releasePointerCapture?.(event.pointerId);
        }

        canvas.addEventListener("pointerup", endCanvasDrag);
        canvas.addEventListener("pointercancel", endCanvasDrag);
        canvas.addEventListener("pointerleave", () => {
            if (!activeDrag) canvas.style.cursor = "";
        });

        backgroundButtons.forEach((button) => {
            button.addEventListener("click", () => {
                state.background = button.dataset.studioBackground || "cream";
                backgroundButtons.forEach((node) => node.classList.toggle("is-active", node === button));
                renderStudioCanvas();
            });
        });

        textPresetButtons.forEach((button) => {
            button.addEventListener("click", () => {
                state.text = button.dataset.studioText || "나 불렀개?";
                state.showText = true;
                state.selectedElement = "text";
                state.selectedStickerId = null;
                if (textInput) textInput.value = state.text;
                textPresetButtons.forEach((node) => node.classList.toggle("is-active", node === button));
                updateStickerButtons();
                renderStudioCanvas();
            });
        });

        if (textInput) {
            textInput.addEventListener("input", () => {
                state.text = textInput.value || "";
                state.showText = true;
                state.selectedElement = "text";
                state.selectedStickerId = null;
                textPresetButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.studioText === state.text));
                updateStickerButtons();
                renderStudioCanvas();
            });
        }

        function selectOrCreateSpeechBubble() {
            let sticker = selectedSticker();
            if (!sticker || sticker.type !== "speechbubble") {
                sticker = makeSticker("speechbubble", { x: 500, y: 160 });
                state.stickers.push(sticker);
            }
            state.selectedElement = "sticker";
            state.selectedStickerId = sticker.id;
            updateStickerButtons();
            return sticker;
        }

        if (bubbleTextInput) {
            bubbleTextInput.addEventListener("input", () => {
                const sticker = selectOrCreateSpeechBubble();
                sticker.bubbleText = bubbleTextInput.value || "";
                renderStudioCanvas();
            });
        }

        if (bubbleSizeInput) {
            bubbleSizeInput.addEventListener("input", () => {
                const sticker = selectOrCreateSpeechBubble();
                sticker.bubbleTextSize = clampStudioValue(Number(bubbleSizeInput.value) || 28, 18, 48);
                renderStudioCanvas();
            });
        }

        colorButtons.forEach((button) => {
            button.addEventListener("click", () => {
                state.textColor = button.dataset.studioColor || "#ffffff";
                state.selectedElement = "text";
                state.selectedStickerId = null;
                colorButtons.forEach((node) => node.classList.toggle("is-active", node === button));
                updateStickerButtons();
                renderStudioCanvas();
            });
        });

        stickerButtons.forEach((button) => {
            button.addEventListener("click", () => addSticker(button.dataset.studioSticker || "imagecrown"));
        });

        if (fileInput) {
            fileInput.addEventListener("change", () => {
                const file = fileInput.files && fileInput.files[0];
                if (!file) return;
                const image = new Image();
                const url = URL.createObjectURL(file);
                image.onload = () => {
                    state.image = image;
                    URL.revokeObjectURL(url);
                    renderStudioCanvas();
                };
                image.onerror = () => {
                    URL.revokeObjectURL(url);
                    showToast("사진을 불러오지 못했어요.");
                };
                image.src = url;
            });
        }

        if (speechBubbleImage && !speechBubbleImage.complete) {
            speechBubbleImage.addEventListener("load", () => renderStudioCanvas(), { once: true });
        }
        Object.values(imageStickers).forEach((image) => {
            if (image && !image.complete) {
                image.addEventListener("load", () => renderStudioCanvas(), { once: true });
            }
        });

        downloadButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const petName = (bootstrap.profile?.pet_name || "dog").replace(/[^\w가-힣-]+/g, "_");
                renderStudioCanvas({ showControls: false });
                downloadCanvas(canvas, `${petName}_이모티콘.png`);
                renderStudioCanvas();
                showToast("이모티콘 PNG를 저장했어요.");
            });
        });

        addSticker("imagecrown");
        state.selectedElement = "text";
        state.selectedStickerId = null;
        updateStickerButtons();
        renderStudioCanvas();
    }

    function closeAllPanels() {
        Object.keys(panels).forEach(closePanel);
    }

    function activateNav(action) {
        document.querySelectorAll("[data-nav-action]").forEach((node) => {
            node.classList.remove("is-active");
        });
        document
            .querySelectorAll(`[data-nav-action="${action}"]`)
            .forEach((node) => node.classList.add("is-active"));
    }

    function handleNavAction(action, chatUsername = "") {
        if (!action) return;

        if (action === "home") {
            if (page === "home") {
                window.scrollTo({ top: 0, behavior: "smooth" });
                activateNav("home");
            } else {
                window.location.href = "/";
            }
            return;
        }

        if (action === "profile") {
            if (page !== "profile") window.location.href = "/profile";
            return;
        }

        if (action === "explore") {
            if (page !== "home") {
                window.location.href = "/#explore-section";
                return;
            }
            const section = document.getElementById("explore-section");
            if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
            activateNav("explore");
            return;
        }

        if (action === "upload") {
            if (page !== "home") {
                window.location.href = "/";
                return;
            }
            const section = document.getElementById("composer-section");
            if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
            if (activityInput) window.setTimeout(() => activityInput.focus(), 120);
            activateNav("upload");
            return;
        }

        if (action === "search") {
            openPanel("search");
            const searchInput = document.getElementById("search-input");
            if (searchInput) window.setTimeout(() => searchInput.focus(), 60);
            loadProfileSearch();
            activateNav("search");
            return;
        }

        if (action === "alerts") {
            openPanel("alerts");
            loadNotifications({ markRead: true });
            activateNav("alerts");
            return;
        }

        if (action === "messages") {
            openPanel("messages");
            renderThreads();
            loadThreads(chatUsername, false, true);
            startMessageRefresh();
            activateNav("messages");
            return;
        }

        if (action === "settings") {
            openPanel("profile");
        }
    }

    function initNav() {
        document.addEventListener("click", (event) => {
            const actionNode = event.target.closest("[data-nav-action]");
            if (actionNode && !actionNode.matches("a")) {
                event.preventDefault();
                handleNavAction(actionNode.dataset.navAction, actionNode.dataset.chatUsername || "");
            }

            const closeNode = event.target.closest(".js-close-panel");
            if (closeNode) {
                closePanel(closeNode.dataset.closeTarget.replace("-modal", "").replace("-panel", ""));
            }

            const backdrop = event.target.classList.contains("overlay-panel") ? event.target : null;
            if (backdrop?.id === "search-panel") closePanel("search");
            if (backdrop?.id === "profile-modal") closePanel("profile");
            if (backdrop?.id === "post-detail-modal") closePanel("post-detail");

            const scrollTarget = event.target.closest(".js-scroll-target");
            if (scrollTarget) {
                const targetId = scrollTarget.dataset.targetId;
                const target = document.getElementById(targetId);
                if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
            }

            const messageButton = event.target.closest(".js-open-message");
            if (messageButton) {
                event.preventDefault();
                openPanel("messages");
                renderThreads();
                loadThreads(messageButton.dataset.username || "", false, true);
                startMessageRefresh();
                activateNav("messages");
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeAllPanels();
        });
    }

    function initUploadForm() {
        if (!fileInput) return;

        if (filePickerButton) {
            filePickerButton.addEventListener("click", () => fileInput.click());
        }

        document.querySelectorAll(".js-use-daily-mission").forEach((button) => {
            button.addEventListener("click", () => {
                const prompt = button.dataset.missionPrompt || "";
                if (!activityInput || !prompt) return;
                activityInput.value = prompt.slice(0, activityInput.maxLength || 320);
                activityInput.focus();
                activityInput.dispatchEvent(new Event("input", { bubbles: true }));
                showToast("오늘의 미션을 활동 메모에 넣었어요.");
            });
        });

        fileInput.addEventListener("change", () => {
            if (!fileName) return;
            fileName.textContent =
                fileInput.files && fileInput.files[0]
                    ? `${fileInput.files[0].name} 준비 완료`
                    : "오늘 올릴 강아지 사진을 선택해 주세요";
            if (uploadPreviewImage) {
                const file = fileInput.files && fileInput.files[0];
                if (file) {
                    uploadPreviewImage.src = URL.createObjectURL(file);
                    uploadPreviewImage.hidden = false;
                } else {
                    uploadPreviewImage.removeAttribute("src");
                    uploadPreviewImage.hidden = true;
                }
            }
        });

        const form = document.getElementById("uploadForm");
        if (!form) return;

        document.querySelectorAll(".js-preview-caption").forEach((button) => {
            button.addEventListener("click", async () => {
                if (!fileInput.files || !fileInput.files.length) {
                    showToast("캡션을 만들 사진을 먼저 선택해 주세요.");
                    return;
                }
                const activityText = activityInput ? activityInput.value.trim() : "";
                if (!activityText) {
                    showToast("오늘 한 활동을 먼저 적어주세요.");
                    if (activityInput) activityInput.focus();
                    return;
                }

                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                formData.append("activity_text", activityText);

                button.disabled = true;
                setLoading("AI가 페르소나를 반영해서 캡션을 만드는 중이에요...");
                try {
                    const response = await fetch("/api/caption-preview", { method: "POST", body: formData });
                    const data = await response.json();
                    if (!response.ok) {
                        showToast(data.error || "캡션 생성에 실패했어요.");
                        return;
                    }

                    const previewBox = document.getElementById("caption-preview-box");
                    const previewInput = document.getElementById("caption-preview-input");
                    if (previewBox) previewBox.hidden = false;
                    if (previewInput) previewInput.value = normalizeAiText(data.caption_text || "");
                    showToast("AI 캡션을 만들었어요.");
                } catch (error) {
                    showToast("캡션 생성 중 오류가 발생했어요.");
                } finally {
                    button.disabled = false;
                    hideLoading();
                }
            });
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!fileInput.files || !fileInput.files.length) {
                showToast("사진을 먼저 선택해 주세요.");
                return;
            }

            const activityText = activityInput ? activityInput.value.trim() : "";
            if (!activityText) {
                showToast("오늘 무엇을 했는지 적어주세요.");
                if (activityInput) activityInput.focus();
                return;
            }

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("activity_text", activityText);
            const previewInput = document.getElementById("caption-preview-input");
            if (previewInput && previewInput.value.trim()) {
                formData.append("caption_override", previewInput.value.trim());
            }

            setLoading("게시물을 올리고 캡션을 준비하는 중이에요...");
            try {
                const response = await fetch("/upload", { method: "POST", body: formData });
                const data = await response.json();
                if (!response.ok) {
                    showToast(data.error || "업로드에 실패했어요.");
                    return;
                }
                showToast("새 게시물이 업로드됐어요.");
                prependPost(data.post);
                resetUploadForm();
                if (data.caption_pending) pollPendingCaption(data.post?.id);
            } catch (error) {
                showToast("업로드 중 오류가 발생했어요.");
            } finally {
                hideLoading();
            }
        });
    }

    function syncLikeState(postId, likes, liked) {
        document.querySelectorAll(`.js-like-button[data-post-id="${CSS.escape(String(postId))}"]`).forEach((button) => {
            button.dataset.liked = liked ? "true" : "false";
            button.classList.toggle("is-liked", liked);
        });

        document.querySelectorAll(`[data-like-count-for="${CSS.escape(String(postId))}"]`).forEach((node) => {
            node.textContent = likes;
        });

        const likeCount = document.getElementById(`like-count-${postId}`);
        if (likeCount) likeCount.textContent = likes;
        if (activeDetailPostId === String(postId)) {
            const detailLikes = document.getElementById("detail-post-likes");
            const detailLike = document.querySelector(".js-detail-like-post");
            if (detailLikes) detailLikes.textContent = likes;
            if (detailLike) detailLike.classList.toggle("is-liked", liked);
            if (activeDetailPost) {
                activeDetailPost.likes = likes;
                activeDetailPost.liked_by_viewer = liked;
            }
        }
    }

    function syncCommentCount(postId) {
        const countNode = document.getElementById(`comment-count-${postId}`);
        if (!countNode) return;
        const list = document.getElementById(`comment-list-${postId}`);
        const count = list
            ? list.querySelectorAll(".comment-item").length
            : activeDetailPostId === String(postId) && activeDetailPost
                ? (activeDetailPost.comments || []).length
                : Number(countNode.textContent || 0);
        countNode.textContent = String(count);
    }

    function syncBookmarkState(postId, bookmarked, bookmarkCount) {
        document.querySelectorAll(`.js-bookmark-button[data-post-id="${CSS.escape(String(postId))}"]`).forEach((button) => {
            button.dataset.bookmarked = bookmarked ? "true" : "false";
            button.classList.toggle("is-bookmarked", bookmarked);
        });

        document.querySelectorAll("[data-bookmark-count]").forEach((node) => {
            node.textContent = bookmarkCount;
        });

        if (activeDetailPostId === String(postId)) {
            const detailBookmark = document.querySelector(".js-detail-bookmark-post");
            if (detailBookmark) detailBookmark.classList.toggle("is-bookmarked", bookmarked);
            if (activeDetailPost) activeDetailPost.bookmarked_by_viewer = bookmarked;
        }
    }

    function normalizeComment(comment) {
        if (typeof comment === "string") {
            return { id: "", post_id: "", content: comment, content_text: "", time_label: "", can_edit: false };
        }
        return comment || { id: "", post_id: "", content: "", content_text: "", time_label: "", can_edit: false };
    }

    function renderCommentItem(comment, postId = "") {
        const data = normalizeComment(comment);
        const item = document.createElement("div");
        item.className = "comment-item";
        if (data.id) item.dataset.commentId = data.id;
        if (postId || data.post_id) item.dataset.postId = postId || data.post_id;
        if (data.content_text) item.dataset.contentText = data.content_text;

        const main = document.createElement("div");
        main.className = "comment-main";
        main.innerHTML = data.content || "";
        item.appendChild(main);

        const meta = document.createElement("div");
        meta.className = "comment-meta";
        const time = document.createElement("span");
        time.textContent = data.time_label || "";
        meta.appendChild(time);

        if (data.can_edit && data.id) {
            const editButton = document.createElement("button");
            editButton.type = "button";
            editButton.className = "comment-tool js-edit-comment";
            editButton.dataset.commentId = data.id;
            editButton.textContent = "수정";
            const deleteButton = document.createElement("button");
            deleteButton.type = "button";
            deleteButton.className = "comment-tool danger-text-button js-delete-comment";
            deleteButton.dataset.commentId = data.id;
            deleteButton.textContent = "삭제";
            meta.append(editButton, deleteButton);
        }

        item.appendChild(meta);
        return item;
    }

    function addCommentToLists(postId, comment) {
        const list = document.getElementById(`comment-list-${postId}`);
        if (list) list.appendChild(renderCommentItem(comment, postId));

        const detailList = activeDetailPostId === String(postId) ? document.getElementById("detail-post-comments") : null;
        if (detailList) detailList.appendChild(renderCommentItem(comment, postId));

        if (activeDetailPostId === String(postId) && activeDetailPost) {
            activeDetailPost.comments = [...(activeDetailPost.comments || []), comment];
        }
        syncCommentCount(postId);
    }

    function updateCommentInLists(comment) {
        const data = normalizeComment(comment);
        if (!data.id) return;
        document.querySelectorAll(`.comment-item[data-comment-id="${CSS.escape(String(data.id))}"]`).forEach((item) => {
            const replacement = renderCommentItem(data, data.post_id);
            item.replaceWith(replacement);
        });
        if (activeDetailPost?.comments) {
            activeDetailPost.comments = activeDetailPost.comments.map((item) => {
                const current = normalizeComment(item);
                return String(current.id) === String(data.id) ? data : item;
            });
        }
    }

    function removeCommentFromLists(commentId, postId) {
        document.querySelectorAll(`.comment-item[data-comment-id="${CSS.escape(String(commentId))}"]`).forEach((item) => item.remove());
        if (activeDetailPostId === String(postId) && activeDetailPost) {
            activeDetailPost.comments = (activeDetailPost.comments || []).filter((item) => {
                const current = normalizeComment(item);
                return String(current.id) !== String(commentId);
            });
        }
        syncCommentCount(postId);
    }

    async function likePost(postId) {
        try {
            const response = await fetch(`/like/${postId}`, { method: "POST" });
            const data = await response.json();
            if (!response.ok) {
                showToast("좋아요 반영에 실패했어요.");
                return;
            }
            syncLikeState(postId, data.likes, data.liked);
        } catch (error) {
            showToast("좋아요 반영에 실패했어요.");
        }
    }

    async function toggleBookmark(postId) {
        try {
            const response = await fetch(`/bookmark/${postId}`, { method: "POST" });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "저장 상태를 바꾸지 못했어요.");
                return;
            }
            syncBookmarkState(postId, data.bookmarked, data.bookmark_count || 0);
            showToast(data.bookmarked ? "게시물을 저장했어요." : "저장을 해제했어요.");
        } catch (error) {
            showToast("저장 상태를 바꾸지 못했어요.");
        }
    }

    async function toggleFollow(button) {
        const username = button.dataset.username;
        const isFollowing = button.dataset.following === "true";
        if (!username) return;

        button.disabled = true;
        try {
            const response = await fetch(`/follow/${encodeURIComponent(username)}`, {
                method: isFollowing ? "DELETE" : "POST",
            });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "팔로우 변경에 실패했어요.");
                return;
            }

            document
                .querySelectorAll(`.js-follow-button[data-username="${CSS.escape(username)}"]`)
                .forEach((node) => {
                    node.dataset.following = data.following ? "true" : "false";
                    node.classList.toggle("is-following", data.following);
                    const label = node.querySelector(".follow-label");
                    if (label) label.textContent = data.following ? "팔로잉" : "팔로우";
                });

            document.querySelectorAll("[data-friend-count]").forEach((node) => {
                node.textContent = data.friend_count;
            });

            const friendCard = button.closest(".js-friend-card");
            if (friendCard && !data.following) friendCard.remove();
            showToast(data.following ? "친구 목록에 추가했어요." : "친구 목록에서 뺐어요.");
        } catch (error) {
            showToast("팔로우 변경에 실패했어요.");
        } finally {
            button.disabled = false;
        }
    }

    async function submitComment(postId, targetInput = null) {
        const input = targetInput || document.getElementById(`comment-input-${postId}`) || document.getElementById("detail-comment-input");
        if (!input || !input.value.trim()) {
            showToast("댓글 내용을 입력해 주세요.");
            return;
        }

        try {
            const response = await fetch(`/comment/${postId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: input.value.trim() }),
            });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "댓글 등록에 실패했어요.");
                return;
            }

            addCommentToLists(postId, data.comment);
            input.value = "";
        } catch (error) {
            showToast("댓글 등록에 실패했어요.");
        }
    }

    function startCommentEdit(button) {
        const item = button.closest(".comment-item");
        if (!item || item.querySelector(".comment-edit-form")) return;

        const main = item.querySelector(".comment-main");
        const meta = item.querySelector(".comment-meta");
        const form = document.createElement("div");
        form.className = "comment-edit-form";

        const input = document.createElement("input");
        input.type = "text";
        input.maxLength = 180;
        input.value = item.dataset.contentText || "";
        input.setAttribute("aria-label", "댓글 수정");

        const actions = document.createElement("div");
        actions.className = "comment-edit-actions";
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "ghost-button js-cancel-comment-edit";
        cancelButton.textContent = "취소";
        const saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.className = "primary-button js-save-comment-edit";
        saveButton.dataset.commentId = item.dataset.commentId || "";
        saveButton.textContent = "저장";
        actions.append(cancelButton, saveButton);
        form.append(input, actions);

        if (main) main.hidden = true;
        if (meta) meta.hidden = true;
        item.appendChild(form);
        window.setTimeout(() => {
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }, 40);
    }

    function cancelCommentEdit(button) {
        const item = button.closest(".comment-item");
        if (!item) return;
        const form = item.querySelector(".comment-edit-form");
        if (form) form.remove();
        const main = item.querySelector(".comment-main");
        const meta = item.querySelector(".comment-meta");
        if (main) main.hidden = false;
        if (meta) meta.hidden = false;
    }

    async function saveCommentEdit(button) {
        const item = button.closest(".comment-item");
        const commentId = button.dataset.commentId || item?.dataset.commentId;
        const input = item?.querySelector(".comment-edit-form input");
        const content = input ? input.value.trim() : "";
        if (!content) {
            showToast("댓글 내용을 입력해 주세요.");
            if (input) input.focus();
            return;
        }

        button.disabled = true;
        try {
            const response = await fetch(`/api/comments/${commentId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content }),
            });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "댓글 수정에 실패했어요.");
                return;
            }
            updateCommentInLists(data.comment);
            showToast("댓글을 수정했어요.");
        } catch (error) {
            showToast("댓글 수정에 실패했어요.");
        } finally {
            button.disabled = false;
        }
    }

    async function deleteComment(commentId) {
        const confirmed = window.confirm("이 댓글을 삭제할까요?");
        if (!confirmed) return;

        try {
            const response = await fetch(`/api/comments/${commentId}`, { method: "DELETE" });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "댓글 삭제에 실패했어요.");
                return;
            }
            removeCommentFromLists(data.comment_id, data.post_id);
            showToast("댓글을 삭제했어요.");
        } catch (error) {
            showToast("댓글 삭제에 실패했어요.");
        }
    }

    async function suggestComment(postId, targetInput = null, triggerButton = null) {
        const input = targetInput || document.getElementById(`comment-input-${postId}`) || document.getElementById("detail-comment-input");
        if (!input) return;

        if (triggerButton) triggerButton.disabled = true;
        input.disabled = true;
        try {
            const response = await fetch(`/api/comment-suggestion/${postId}`, { method: "POST" });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "AI 댓글을 만들지 못했어요.");
                return;
            }

            input.value = normalizeAiText(data.comment || "");
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
            showToast("AI 댓글을 준비했어요.");
        } catch (error) {
            showToast("AI 댓글 생성 중 오류가 발생했어요.");
        } finally {
            input.disabled = false;
            if (triggerButton) triggerButton.disabled = false;
        }
    }

    function openPostEditor(postId) {
        const panel = document.getElementById(`post-edit-${postId}`);
        const input = document.getElementById(`post-edit-input-${postId}`);
        if (!panel || !input) return;
        panel.hidden = false;
        window.setTimeout(() => input.focus(), 60);
    }

    function closePostEditor(postId) {
        const panel = document.getElementById(`post-edit-${postId}`);
        if (panel) panel.hidden = true;
    }

    async function updatePostCaption(postId, captionText) {
        const response = await fetch(`/post/${postId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ caption: captionText }),
        });
        const data = await response.json();
        return { ok: response.ok, data };
    }

    async function savePost(postId) {
        const input = document.getElementById(`post-edit-input-${postId}`);
        const captionText = input ? input.value.trim() : "";
        if (!captionText) {
            showToast("수정할 캡션 내용을 입력해 주세요.");
            if (input) input.focus();
            return;
        }

        try {
            const result = await updatePostCaption(postId, captionText);
            if (!result.ok) {
                showToast(result.data.error || "게시물 수정에 실패했어요.");
                return;
            }

            const captionNode = document.getElementById(`caption-text-${postId}`);
            if (captionNode) captionNode.innerHTML = result.data.caption;
            input.value = result.data.caption_text || captionText;
            closePostEditor(postId);
            showToast("게시물을 수정했어요.");
        } catch (error) {
            showToast("게시물 수정에 실패했어요.");
        }
    }

    async function deletePost(postId) {
        const confirmed = window.confirm("이 게시물을 삭제할까요? 피드에서 사진과 댓글이 함께 사라져요.");
        if (!confirmed) return;

        try {
            const response = await fetch(`/post/${postId}`, { method: "DELETE" });
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "게시물 삭제에 실패했어요.");
                return;
            }

            const post = document.getElementById(`post-${postId}`);
            if (post) post.remove();
            document.querySelectorAll(`.js-profile-post-edit[data-post-id="${CSS.escape(String(postId))}"]`).forEach((node) => {
                node.remove();
            });
            if (activeProfilePostId === String(postId)) {
                activeProfilePostId = "";
                closePanel("post-editor");
            }
            if (activeDetailPostId === String(postId)) {
                activeDetailPostId = "";
                activeDetailPost = null;
                closePanel("post-detail");
            }
            showToast("게시물을 삭제했어요.");
        } catch (error) {
            showToast("게시물 삭제에 실패했어요.");
        }
    }

    function setDetailAvatar(post) {
        const avatar = document.getElementById("detail-post-avatar");
        if (!avatar) return;
        avatar.innerHTML = "";
        const avatarUrl = post.display_avatar_url || post.avatar_url;
        if (avatarUrl) {
            const img = document.createElement("img");
            img.src = avatarUrl;
            img.alt = post.pet_name || "프로필";
            avatar.appendChild(img);
        } else {
            const initial = document.createElement("span");
            initial.textContent = post.initial || (post.pet_name || "멍").slice(0, 1);
            avatar.appendChild(initial);
        }
    }

    function renderPostDetail(post) {
        activeDetailPost = post;
        activeDetailPostId = String(post.id);

        const title = document.getElementById("detail-post-title");
        const image = document.getElementById("detail-post-image");
        const name = document.getElementById("detail-post-name");
        const meta = document.getElementById("detail-post-meta");
        const caption = document.getElementById("detail-post-caption");
        const likes = document.getElementById("detail-post-likes");
        const comments = document.getElementById("detail-post-comments");
        const editButton = document.querySelector(".js-detail-edit-post");
        const likeButton = document.querySelector(".js-detail-like-post");
        const bookmarkButton = document.querySelector(".js-detail-bookmark-post");
        const editPanel = document.getElementById("detail-edit-panel");
        const editInput = document.getElementById("detail-edit-input");
        const canEdit = Boolean(post.is_owner);

        if (title) title.textContent = `${post.pet_name || "게시물"}의 게시물`;
        if (image) {
            image.src = post.image_url || "";
            image.alt = `${post.pet_name || "강아지"} 사진`;
        }
        setDetailAvatar(post);
        if (name) name.textContent = post.pet_name || post.username || "";
        if (meta) meta.textContent = `${post.persona || ""} · ${post.time_label || ""}`;
        if (caption) caption.innerHTML = `<strong>${post.pet_name || ""}</strong> ${post.caption || ""}`;
        if (likes) likes.textContent = post.likes || 0;
        if (comments) {
            comments.innerHTML = "";
            (post.comments || []).forEach((comment) => {
                comments.appendChild(renderCommentItem(comment, post.id));
            });
        }
        if (editButton) editButton.hidden = !canEdit;
        if (likeButton) likeButton.classList.toggle("is-liked", Boolean(post.liked_by_viewer));
        if (bookmarkButton) bookmarkButton.classList.toggle("is-bookmarked", Boolean(post.bookmarked_by_viewer));
        if (editPanel) {
            editPanel.hidden = true;
            editPanel.classList.toggle("is-owner-only", !canEdit);
        }
        if (editInput) editInput.value = post.caption_text || "";
        const detailCommentInput = document.getElementById("detail-comment-input");
        if (detailCommentInput) detailCommentInput.value = "";
    }

    async function openPostDetail(postId) {
        try {
            const response = await fetch(`/api/posts/${postId}`);
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "게시물을 불러오지 못했어요.");
                return;
            }
            renderPostDetail(data.post);
            openPanel("post-detail");
        } catch (error) {
            showToast("게시물을 불러오지 못했어요.");
        }
    }

    function openDetailEditor() {
        if (!activeDetailPost?.is_owner) {
            closeDetailEditor();
            showToast("내 게시물만 수정할 수 있어요.");
            return;
        }
        const panel = document.getElementById("detail-edit-panel");
        const input = document.getElementById("detail-edit-input");
        if (!panel || !input || !activeDetailPost) return;
        input.value = activeDetailPost.caption_text || "";
        panel.hidden = false;
        window.setTimeout(() => input.focus(), 60);
    }

    function closeDetailEditor() {
        const panel = document.getElementById("detail-edit-panel");
        if (panel) panel.hidden = true;
    }

    async function saveDetailPost() {
        if (!activeDetailPost?.is_owner) {
            closeDetailEditor();
            showToast("내 게시물만 수정할 수 있어요.");
            return;
        }
        const input = document.getElementById("detail-edit-input");
        const captionText = input ? input.value.trim() : "";
        if (!activeDetailPostId || !captionText) {
            showToast("수정할 캡션 내용을 입력해 주세요.");
            if (input) input.focus();
            return;
        }

        try {
            const result = await updatePostCaption(activeDetailPostId, captionText);
            if (!result.ok) {
                showToast(result.data.error || "게시물 수정에 실패했어요.");
                return;
            }

            const captionNode = document.getElementById(`caption-text-${activeDetailPostId}`);
            if (captionNode) captionNode.innerHTML = result.data.caption;
            document
                .querySelectorAll(`.js-profile-post-edit[data-post-id="${CSS.escape(String(activeDetailPostId))}"], .js-open-post-detail[data-post-id="${CSS.escape(String(activeDetailPostId))}"]`)
                .forEach((node) => {
                    node.dataset.caption = result.data.caption_text || captionText;
                });
            activeDetailPost.caption = result.data.caption;
            activeDetailPost.caption_text = result.data.caption_text || captionText;
            renderPostDetail(activeDetailPost);
            showToast("게시물을 수정했어요.");
        } catch (error) {
            showToast("게시물 수정에 실패했어요.");
        }
    }

    function openProfilePostEditor(button) {
        activeProfilePostId = button.dataset.postId || "";
        const input = document.getElementById("profile-post-edit-input");
        const image = document.getElementById("profile-post-editor-image");
        if (!activeProfilePostId || !input || !image) return;

        input.value = button.dataset.caption || "";
        image.src = button.dataset.imageUrl || "";
        image.alt = "게시물 사진";
        openPanel("post-editor");
        window.setTimeout(() => input.focus(), 80);
    }

    async function saveProfilePost() {
        const input = document.getElementById("profile-post-edit-input");
        const captionText = input ? input.value.trim() : "";
        if (!activeProfilePostId || !captionText) {
            showToast("수정할 캡션 내용을 입력해 주세요.");
            if (input) input.focus();
            return;
        }

        try {
            const result = await updatePostCaption(activeProfilePostId, captionText);
            if (!result.ok) {
                showToast(result.data.error || "게시물 수정에 실패했어요.");
                return;
            }

            document
                .querySelectorAll(`.js-profile-post-edit[data-post-id="${CSS.escape(String(activeProfilePostId))}"]`)
                .forEach((node) => {
                    node.dataset.caption = result.data.caption_text || captionText;
                });
            const captionNode = document.getElementById(`caption-text-${activeProfilePostId}`);
            if (captionNode) captionNode.innerHTML = result.data.caption;
            closePanel("post-editor");
            showToast("게시물을 수정했어요.");
        } catch (error) {
            showToast("게시물 수정에 실패했어요.");
        }
    }

    function initPostActions() {
        document.addEventListener("click", (event) => {
            const likeButton = event.target.closest(".js-like-button");
            if (likeButton) {
                event.preventDefault();
                likePost(likeButton.dataset.postId);
                return;
            }

            const bookmarkButton = event.target.closest(".js-bookmark-button");
            if (bookmarkButton) {
                event.preventDefault();
                toggleBookmark(bookmarkButton.dataset.postId);
                return;
            }

            const followButton = event.target.closest(".js-follow-button");
            if (followButton) {
                event.preventDefault();
                toggleFollow(followButton);
                return;
            }

            const editButton = event.target.closest(".js-edit-post");
            if (editButton) {
                event.preventDefault();
                openPostEditor(editButton.dataset.postId);
                return;
            }

            const cancelEdit = event.target.closest(".js-cancel-edit");
            if (cancelEdit) {
                event.preventDefault();
                closePostEditor(cancelEdit.dataset.postId);
                return;
            }

            const saveButton = event.target.closest(".js-save-post");
            if (saveButton) {
                event.preventDefault();
                savePost(saveButton.dataset.postId);
                return;
            }

            const deleteButton = event.target.closest(".js-delete-post");
            if (deleteButton) {
                event.preventDefault();
                deletePost(deleteButton.dataset.postId);
                return;
            }

            const detailButton = event.target.closest(".js-open-post-detail");
            if (detailButton) {
                event.preventDefault();
                openPostDetail(detailButton.dataset.postId);
                return;
            }

            const profilePost = event.target.closest(".js-profile-post-edit");
            if (profilePost) {
                event.preventDefault();
                openProfilePostEditor(profilePost);
                return;
            }

            const profileSave = event.target.closest(".js-profile-save-post");
            if (profileSave) {
                event.preventDefault();
                saveProfilePost();
                return;
            }

            const profileDelete = event.target.closest(".js-profile-delete-post");
            if (profileDelete && activeProfilePostId) {
                event.preventDefault();
                deletePost(activeProfilePostId);
                return;
            }

            const detailLike = event.target.closest(".js-detail-like-post");
            if (detailLike && activeDetailPostId) {
                event.preventDefault();
                likePost(activeDetailPostId);
                return;
            }

            const detailBookmark = event.target.closest(".js-detail-bookmark-post");
            if (detailBookmark && activeDetailPostId) {
                event.preventDefault();
                toggleBookmark(activeDetailPostId);
                return;
            }

            const detailEdit = event.target.closest(".js-detail-edit-post");
            if (detailEdit) {
                event.preventDefault();
                openDetailEditor();
                return;
            }

            const detailCancel = event.target.closest(".js-detail-cancel-edit");
            if (detailCancel) {
                event.preventDefault();
                closeDetailEditor();
                return;
            }

            const detailSave = event.target.closest(".js-detail-save-post");
            if (detailSave) {
                event.preventDefault();
                saveDetailPost();
                return;
            }

            const detailDelete = event.target.closest(".js-detail-delete-post");
            if (detailDelete && activeDetailPostId) {
                event.preventDefault();
                deletePost(activeDetailPostId);
                return;
            }

            const editCommentButton = event.target.closest(".js-edit-comment");
            if (editCommentButton) {
                event.preventDefault();
                startCommentEdit(editCommentButton);
                return;
            }

            const cancelCommentEditButton = event.target.closest(".js-cancel-comment-edit");
            if (cancelCommentEditButton) {
                event.preventDefault();
                cancelCommentEdit(cancelCommentEditButton);
                return;
            }

            const saveCommentEditButton = event.target.closest(".js-save-comment-edit");
            if (saveCommentEditButton) {
                event.preventDefault();
                saveCommentEdit(saveCommentEditButton);
                return;
            }

            const deleteCommentButton = event.target.closest(".js-delete-comment");
            if (deleteCommentButton) {
                event.preventDefault();
                deleteComment(deleteCommentButton.dataset.commentId);
                return;
            }

            const aiComment = event.target.closest(".js-ai-comment");
            if (aiComment) {
                event.preventDefault();
                suggestComment(aiComment.dataset.postId, null, aiComment);
                return;
            }

            const detailAiComment = event.target.closest(".js-detail-ai-comment");
            if (detailAiComment && activeDetailPostId) {
                event.preventDefault();
                suggestComment(activeDetailPostId, document.getElementById("detail-comment-input"), detailAiComment);
                return;
            }

            const commentSubmit = event.target.closest(".js-comment-submit");
            if (commentSubmit) {
                event.preventDefault();
                submitComment(commentSubmit.dataset.postId);
                return;
            }

            const detailCommentSubmit = event.target.closest(".js-detail-comment-submit");
            if (detailCommentSubmit && activeDetailPostId) {
                event.preventDefault();
                submitComment(activeDetailPostId, document.getElementById("detail-comment-input"));
                return;
            }

            const commentFocus = event.target.closest(".js-comment-focus");
            if (commentFocus) {
                event.preventDefault();
                const input = document.getElementById(`comment-input-${commentFocus.dataset.postId}`);
                if (input) {
                    input.scrollIntoView({ behavior: "smooth", block: "center" });
                    input.focus();
                }
                return;
            }
        });

        document.addEventListener("keydown", (event) => {
            const commentEditInput = event.target.closest(".comment-edit-form input");
            if (commentEditInput) {
                if (event.key === "Escape") {
                    event.preventDefault();
                    const cancelButton = commentEditInput.closest(".comment-edit-form")?.querySelector(".js-cancel-comment-edit");
                    if (cancelButton) cancelCommentEdit(cancelButton);
                    return;
                }
                if (event.key === "Enter") {
                    event.preventDefault();
                    const saveButton = commentEditInput.closest(".comment-edit-form")?.querySelector(".js-save-comment-edit");
                    if (saveButton) saveCommentEdit(saveButton);
                    return;
                }
            }

            const editInput = event.target.closest(".post-edit-panel textarea");
            if (editInput && event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                const postId = editInput.id.replace("post-edit-input-", "");
                event.preventDefault();
                savePost(postId);
                return;
            }

            if (event.key !== "Enter") return;
            const detailInput = event.target.closest("#detail-comment-input");
            if (detailInput && activeDetailPostId) {
                event.preventDefault();
                submitComment(activeDetailPostId, detailInput);
                return;
            }
            const input = event.target.closest(".comment-form input");
            if (!input) return;
            const postId = input.id.replace("comment-input-", "");
            event.preventDefault();
            submitComment(postId);
        });
    }

    function renderProfileSearchResults(profiles) {
        const resultsNode = document.getElementById("profile-search-results");
        if (!resultsNode) return;
        resultsNode.innerHTML = "";

        if (!profiles.length) {
            const empty = document.createElement("div");
            empty.className = "search-empty";
            empty.textContent = "조건에 맞는 강아지를 찾지 못했어요.";
            resultsNode.appendChild(empty);
            return;
        }

        profiles.forEach((profile) => {
            const card = document.createElement("article");
            card.className = "profile-search-card";

            const avatar = document.createElement("span");
            avatar.className = "avatar avatar-small avatar-ring";
            const avatarUrl = profile.display_avatar_url || profile.avatar_url;
            if (avatarUrl) {
                const img = document.createElement("img");
                img.src = avatarUrl;
                img.alt = profile.pet_name || profile.username;
                avatar.appendChild(img);
            } else {
                const initial = document.createElement("span");
                initial.textContent = profile.initial || (profile.pet_name || profile.username || "?").slice(0, 1);
                avatar.appendChild(initial);
            }

            const copy = document.createElement("span");
            copy.className = "profile-search-copy";
            const name = document.createElement("a");
            name.className = "profile-name-link";
            name.href = `/profile/${encodeURIComponent(profile.username)}`;
            const nameStrong = document.createElement("strong");
            nameStrong.textContent = profile.pet_name || profile.username;
            name.appendChild(nameStrong);
            const meta = document.createElement("small");
            meta.textContent = `${profile.persona || ""} · ${profile.pet_species || ""}`;
            const status = document.createElement("span");
            status.textContent = profile.status_message || profile.handle || "";
            const stats = document.createElement("small");
            stats.textContent = `${profile.posts_count || 0} 게시물 · ${profile.total_likes || 0} 좋아요 · ${profile.last_post_label || "활동 없음"}`;
            const reasons = document.createElement("span");
            reasons.className = "match-reasons";
            reasons.textContent = (profile.match_reasons || []).join(" · ");
            const summary = document.createElement("span");
            summary.className = "match-summary";
            summary.textContent = profile.match_summary || "";
            copy.append(name, meta, status, stats, reasons, summary, createBadgeRow(profile.badges, "mini"));

            const actions = document.createElement("span");
            actions.className = "profile-search-actions";
            const score = document.createElement("em");
            score.className = "match-chip";
            score.textContent = `${profile.match_score}% ${profile.match_label}`;
            actions.appendChild(score);

            if (!profile.is_me) {
                const follow = document.createElement("button");
                follow.type = "button";
                follow.className = `follow-button js-follow-button ${profile.is_following ? "is-following" : ""}`;
                follow.dataset.username = profile.username;
                follow.dataset.following = profile.is_following ? "true" : "false";
                const label = document.createElement("span");
                label.className = "follow-label";
                label.textContent = profile.is_following ? "팔로잉" : "팔로우";
                follow.appendChild(label);
                actions.appendChild(follow);
            }

            card.append(avatar, copy, actions);
            resultsNode.appendChild(card);
        });
    }

    async function loadProfileSearch() {
        const input = document.getElementById("search-input");
        const personaSelect = document.getElementById("search-persona");
        const sortSelect = document.getElementById("search-sort");
        const params = new URLSearchParams();
        if (input?.value.trim()) params.set("q", input.value.trim());
        if (personaSelect?.value) params.set("persona", personaSelect.value);
        if (sortSelect?.value) params.set("sort", sortSelect.value);

        try {
            const response = await fetch(`/api/profile-search${params.toString() ? `?${params}` : ""}`);
            const data = await response.json();
            if (!response.ok) {
                showToast(data.error || "프로필 검색에 실패했어요.");
                return;
            }
            renderProfileSearchResults(data.profiles || []);
        } catch (error) {
            showToast("프로필 검색에 실패했어요.");
        }
    }

    function initSearch() {
        const input = document.getElementById("search-input");
        const personaSelect = document.getElementById("search-persona");
        const sortSelect = document.getElementById("search-sort");
        if (!input && !personaSelect && !sortSelect) return;

        let searchTimer = null;
        const scheduleSearch = () => {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(loadProfileSearch, 180);
        };

        if (input) input.addEventListener("input", scheduleSearch);
        if (personaSelect) personaSelect.addEventListener("change", loadProfileSearch);
        if (sortSelect) sortSelect.addEventListener("change", loadProfileSearch);
    }

    async function saveProfile(formData) {
        const response = await fetch("/api/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(formData),
        });
        return response.json().then((data) => ({ ok: response.ok, data }));
    }

    async function uploadProfileAvatar(file) {
        const formData = new FormData();
        formData.append("avatar", file);
        const response = await fetch("/api/profile/avatar", {
            method: "POST",
            body: formData,
        });
        return response.json().then((data) => ({ ok: response.ok, data }));
    }

    function initProfileForm() {
        const form = document.getElementById("profile-form");
        if (!form) return;
        const avatarInput = document.getElementById("profile-avatar-file");
        const avatarFileName = document.getElementById("profile-avatar-file-name");
        const avatarPreview = document.getElementById("profile-avatar-preview");
        const avatarInitial = document.getElementById("profile-avatar-initial");

        if (avatarInput) {
            avatarInput.addEventListener("change", () => {
                const file = avatarInput.files && avatarInput.files[0];
                if (!file) return;
                if (avatarFileName) avatarFileName.textContent = file.name;
                if (avatarPreview) {
                    avatarPreview.src = URL.createObjectURL(file);
                    avatarPreview.hidden = false;
                }
                if (avatarInitial) avatarInitial.hidden = true;
            });
        }

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const payload = Object.fromEntries(new FormData(form).entries());
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true;

            if (avatarInput?.files?.[0]) {
                const uploadResult = await uploadProfileAvatar(avatarInput.files[0]);
                if (!uploadResult.ok) {
                    if (submitButton) submitButton.disabled = false;
                    showToast(uploadResult.data.error || "프로필 사진 업로드에 실패했어요.");
                    return;
                }
                payload.avatar_url = uploadResult.data.avatar_url;
            }

            const result = await saveProfile(payload);
            if (submitButton) submitButton.disabled = false;

            if (!result.ok) {
                showToast(result.data.error || "프로필 저장에 실패했어요.");
                return;
            }

            showToast("프로필이 저장됐어요.");
            window.setTimeout(() => window.location.reload(), 450);
        });
    }

    function startMessageRefresh() {
        stopMessageRefresh();
        messageRefreshTimer = window.setInterval(() => {
            if (panels.messages?.classList.contains("open")) loadThreads("", true, true);
        }, 4000);
    }

    function stopMessageRefresh() {
        if (!messageRefreshTimer) return;
        window.clearInterval(messageRefreshTimer);
        messageRefreshTimer = null;
    }

    async function loadThreads(preferredUsername = "", silent = false, markRead = false) {
        try {
            const params = new URLSearchParams();
            if (markRead) params.set("mark_read", "1");
            if (preferredUsername) params.set("partner", preferredUsername);
            const response = await fetch(`/api/messages${params.toString() ? `?${params}` : ""}`);
            const data = await response.json();
            if (!response.ok) {
                if (!silent) showToast(data.error || "메시지를 불러오지 못했어요.");
                return;
            }

            const currentUsername = preferredUsername || threads[activeThreadIndex]?.username || "";
            threads = normalizeThreads(data.threads || []);
            const nextIndex = threads.findIndex((thread) => thread.username === currentUsername);
            activeThreadIndex = nextIndex >= 0 ? nextIndex : 0;
            unreadMessageCount = data.unread_count || 0;
            renderThreads();
            updateMessageBadges();
        } catch (error) {
            if (!silent) showToast("메시지를 불러오지 못했어요.");
        }
    }

    function renderThreads() {
        const listNode = document.getElementById("message-thread-list");
        const roomNode = document.getElementById("message-room-body");
        const form = document.getElementById("message-form");
        const input = document.getElementById("message-input");
        if (!listNode || !roomNode) return;

        listNode.innerHTML = "";
        roomNode.innerHTML = "";

        if (!threads.length) {
            const empty = document.createElement("div");
            empty.className = "message-empty";
            empty.textContent = "팔로우한 친구가 생기면 여기서 메시지를 보낼 수 있어요.";
            listNode.appendChild(empty);

            const guide = document.createElement("div");
            guide.className = "message-room-empty";
            guide.textContent = "친구 목록에서 메시지 버튼을 눌러 대화를 시작하세요.";
            roomNode.appendChild(guide);
            if (form) form.hidden = true;
            return;
        }

        if (activeThreadIndex >= threads.length) activeThreadIndex = 0;
        threads.forEach((thread, index) => {
            const button = document.createElement("button");
            button.className = `thread-button ${index === activeThreadIndex ? "is-active" : ""}`;
            button.type = "button";
            button.dataset.threadIndex = String(index);

            const avatar = createAvatarNode(thread);
            const copy = document.createElement("span");
            copy.className = "thread-copy";
            const name = document.createElement("strong");
            name.textContent = thread.name || thread.username;
            const handle = document.createElement("span");
            handle.textContent = thread.last_message || thread.handle || "";
            copy.append(name, handle);

            const meta = document.createElement("span");
            meta.className = "thread-meta";
            meta.textContent = formatShortTime(thread.last_time);

            button.append(avatar, copy, meta);
            if (thread.unread_count) {
                const badge = document.createElement("em");
                badge.className = "thread-unread";
                badge.textContent = thread.unread_count > 9 ? "9+" : String(thread.unread_count);
                button.appendChild(badge);
            }
            listNode.appendChild(button);
        });

        const activeThread = threads[activeThreadIndex];
        const roomHeader = document.createElement("div");
        roomHeader.className = "message-room-head";
        roomHeader.appendChild(createAvatarNode(activeThread));
        const roomTitle = document.createElement("div");
        const roomName = document.createElement("strong");
        roomName.textContent = activeThread.name || activeThread.username;
        const roomHandle = document.createElement("span");
        roomHandle.textContent = activeThread.handle || `@${activeThread.username}`;
        roomTitle.append(roomName, roomHandle);
        roomHeader.appendChild(roomTitle);
        roomNode.appendChild(roomHeader);

        if (!activeThread.messages.length) {
            const guide = document.createElement("div");
            guide.className = "message-room-empty";
            guide.textContent = `${activeThread.name || activeThread.username}님에게 첫 메시지를 보내보세요.`;
            roomNode.appendChild(guide);
        } else {
            activeThread.messages.forEach((message) => {
                const row = document.createElement("div");
                row.className = `message-row ${message.is_me ? "me" : "friend"}`;

                const bubble = document.createElement("div");
                bubble.className = "bubble";
                const text = document.createElement("span");
                text.textContent = message.body || "";
                const time = document.createElement("small");
                time.textContent = formatShortTime(message.created_at);
                bubble.append(text, time);
                row.appendChild(bubble);
                roomNode.appendChild(row);
            });
        }

        if (input) input.placeholder = `${activeThread.name || "친구"}에게 메시지 보내기`;
        if (form) form.hidden = false;
        roomNode.scrollTop = roomNode.scrollHeight;
    }

    function ensureMessageTonePreview(form) {
        let node = document.getElementById("message-tone-preview");
        if (node || !form?.parentNode) return node;

        node = document.createElement("div");
        node.id = "message-tone-preview";
        node.className = "message-tone-preview";
        node.hidden = true;
        form.parentNode.insertBefore(node, form);
        return node;
    }

    function clearMessageToneSuggestions() {
        window.clearTimeout(messageToneTimer);
        messageToneRequestId += 1;
        lastMessageToneBody = "";
        const node = document.getElementById("message-tone-preview");
        if (!node) return;
        node.hidden = true;
        node.innerHTML = "";
    }

    function hideMessageToneSuggestions() {
        window.clearTimeout(messageToneTimer);
        messageToneRequestId += 1;
        lastMessageToneBody = "";
        const node = document.getElementById("message-tone-preview");
        if (!node) return;
        node.hidden = true;
        node.innerHTML = "";
    }

    function renderMessageToneSuggestions(suggestions, sourceBody = "") {
        const form = document.getElementById("message-form");
        const node = ensureMessageTonePreview(form);
        if (!node) return;

        const cleanSuggestions = [
            ...new Set((suggestions || []).map((suggestion, index) => expandShortAiTone(suggestion, index)).filter(Boolean)),
        ];

        if (!cleanSuggestions.length) {
            if (!node.innerHTML.trim()) node.hidden = true;
            return;
        }

        if (sourceBody && sourceBody !== (document.getElementById("message-input")?.value.trim() || "")) {
            return;
        }

        lastMessageToneBody = sourceBody || lastMessageToneBody;
        node.innerHTML = "";

        const label = document.createElement("span");
        label.className = "message-tone-label";
        label.textContent = "말투 제안";
        node.appendChild(label);

        cleanSuggestions.forEach((suggestion) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "message-tone-chip";
            button.dataset.toneText = suggestion;
            button.textContent = suggestion;
            node.appendChild(button);
        });
        node.hidden = false;
    }

    function localMessageToneSuggestions(body) {
        const text = normalizeAiText(body);
        const compact = text.replace(/[\s!~.,]+/g, "");
        const common = {
            "안녕하세요": ["안녕하개", "안녕하세요멍", "반갑개"],
            "안녕": ["안녕하개", "안녕멍", "반갑개"],
            "하이": ["하이멍", "반갑개", "안녕하개"],
            "뭐해": ["뭐하개?", "뭐 하냐멍?", "지금 뭐 해멍?"],
            "산책가자": ["산책 가자멍", "같이 나가개", "바깥 구경 가자멍"],
            "놀자": ["같이 놀자멍", "놀자개", "한 번 더 놀개?"],
            "고마워": ["고맙다멍", "고맙개", "정말 고마워멍"],
        };
        if (common[compact]) return common[compact].map(expandShortAiTone);

        const plain = text.split(/[,，]/, 1)[0].trim();
        const question = plain.endsWith("?");
        const base = plain.replace(/[!?~.]+$/g, "").trim();
        let meongText = base;
        if (!/[멍개]$/.test(meongText)) {
            if (meongText.endsWith("해요")) meongText = `${meongText.slice(0, -2)}한다멍`;
            else if (meongText.endsWith("요")) meongText = `${meongText.slice(0, -1)}멍`;
            else if (meongText.endsWith("해")) meongText = `${meongText.slice(0, -1)}한다멍`;
            else meongText = `${meongText}멍`;
        }
        if (question) meongText += "?";

        let gaeText = base;
        const replacements = [
            ["하세요", "하개"],
            ["해요", "하개"],
            ["해줘", "해주개"],
            ["할래", "할개"],
            ["갈래", "갈개"],
            ["해", "하개"],
            ["가자", "가개"],
            ["보자", "보개"],
            ["놀자", "놀개"],
            ["고마워", "고맙개"],
            ["좋아", "좋개"],
        ];
        if (!/[멍개]$/.test(gaeText)) {
            const replacement = replacements.find(([before]) => gaeText.endsWith(before));
            gaeText = replacement
                ? `${gaeText.slice(0, -replacement[0].length)}${replacement[1]}`
                : `${gaeText}개`;
        }
        if (question) gaeText += "?";
        return [...new Set([meongText, gaeText])].map(expandShortAiTone).filter(Boolean);
    }

    function scheduleMessageTonePreview() {
        window.clearTimeout(messageToneTimer);
        const input = document.getElementById("message-input");
        const activeThread = threads[activeThreadIndex];
        const body = input?.value.trim() || "";
        if (!body) {
            hideMessageToneSuggestions();
            return;
        }

        if (body !== lastMessageToneBody) {
            renderMessageToneSuggestions(localMessageToneSuggestions(body), body);
        }

        if (!activeThread) return;

        const requestId = ++messageToneRequestId;
        messageToneTimer = window.setTimeout(async () => {
            try {
                const response = await fetch("/api/messages/tone-preview", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ partner: activeThread.username, body }),
                });
                const data = await response.json();
                if (requestId !== messageToneRequestId) return;
                if (!response.ok) {
                    return;
                }
                renderMessageToneSuggestions(data.suggestions || [], body);
            } catch (error) {
                return;
            }
        }, 260);
    }

    function initMessages() {
        const threadList = document.getElementById("message-thread-list");
        const form = document.getElementById("message-form");
        const input = document.getElementById("message-input");
        if (!threadList || !form || !input) return;
        const tonePreview = ensureMessageTonePreview(form);

        threadList.addEventListener("click", (event) => {
            const button = event.target.closest("[data-thread-index]");
            if (!button) return;
            activeThreadIndex = Number(button.dataset.threadIndex);
            const selectedThread = threads[activeThreadIndex];
            renderThreads();
            clearMessageToneSuggestions();
            if (selectedThread?.unread_count) loadThreads(selectedThread.username, true, true);
        });

        if (tonePreview) {
            tonePreview.addEventListener("click", (event) => {
                const button = event.target.closest(".message-tone-chip");
                if (!button) return;
                input.value = button.dataset.toneText || button.textContent || "";
                clearMessageToneSuggestions();
                input.focus();
            });
        }

        input.addEventListener("input", scheduleMessageTonePreview);
        input.addEventListener("keyup", scheduleMessageTonePreview);
        input.addEventListener("change", scheduleMessageTonePreview);
        input.addEventListener("compositionend", scheduleMessageTonePreview);
        input.addEventListener("paste", () => window.setTimeout(scheduleMessageTonePreview, 0));
        input.addEventListener("focus", scheduleMessageTonePreview);

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const value = input.value.trim();
            if (!value) return;
            const activeThread = threads[activeThreadIndex];
            if (!activeThread) return;

            input.disabled = true;
            try {
                const response = await fetch(`/api/messages/${encodeURIComponent(activeThread.username)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ body: value }),
                });
                const data = await response.json();
                if (!response.ok) {
                    showToast(data.error || "메시지를 보내지 못했어요.");
                    return;
                }

                activeThread.messages.push(data.message);
                activeThread.last_message = data.message.body;
                activeThread.last_time = data.message.created_at;
                activeThread.unread_count = 0;
                input.value = "";
                clearMessageToneSuggestions();
                renderThreads();
            } catch (error) {
                showToast("메시지를 보내지 못했어요.");
            } finally {
                input.disabled = false;
                input.focus();
            }
        });

        renderThreads();
    }

    function notificationNodes() {
        return [
            ...document.querySelectorAll(".notification-list"),
            ...document.querySelectorAll("#alerts-panel .drawer-list"),
        ];
    }

    function notificationIcon(type) {
        return {
            like: "fa-solid fa-heart",
            comment: "fa-regular fa-comment",
            follow: "fa-solid fa-user-plus",
            message: "fa-regular fa-paper-plane",
        }[type] || "fa-regular fa-bell";
    }

    function renderNotifications() {
        notificationNodes().forEach((list) => {
            list.innerHTML = "";
            if (!notifications.length) {
                const empty = document.createElement(list.tagName === "UL" ? "li" : "article");
                empty.className = "notification-empty";
                empty.textContent = "아직 새 알림이 없어요.";
                list.appendChild(empty);
                return;
            }

            notifications.forEach((item) => {
                const node = document.createElement(list.tagName === "UL" ? "li" : "article");
                if (list.tagName !== "UL") node.className = `drawer-item notification-item ${item.is_read ? "" : "is-unread"}`;
                if (list.tagName === "UL") node.className = `notification-item ${item.is_read ? "" : "is-unread"}`;

                const title = document.createElement("strong");
                const icon = document.createElement("i");
                icon.className = notificationIcon(item.type);
                title.append(icon, ` ${item.title || "새 알림"}`);

                const body = document.createElement(list.tagName === "UL" ? "span" : "p");
                body.textContent = item.body || "";
                const time = document.createElement("small");
                time.className = "notification-time";
                time.textContent = formatShortTime(item.created_at);

                if (item.link) {
                    const link = document.createElement("a");
                    link.href = item.link;
                    link.append(title, body, time);
                    node.appendChild(link);
                } else {
                    node.append(title, body, time);
                }
                list.appendChild(node);
            });
        });
    }

    function updateNotificationBadges() {
        document.querySelectorAll('[data-nav-action="alerts"]').forEach((node) => {
            let badge = node.querySelector(".notification-badge");
            node.classList.toggle("has-unread", Boolean(unreadNotificationCount));
            if (!unreadNotificationCount) {
                if (badge) badge.remove();
                return;
            }
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "notification-badge";
                node.appendChild(badge);
            }
            badge.textContent = unreadNotificationCount > 9 ? "9+" : String(unreadNotificationCount);
        });
        updateRealtimeStatus();
        updatePageTitle();
    }

    function updateMessageBadges() {
        document.querySelectorAll('[data-nav-action="messages"], .js-open-message').forEach((node) => {
            let badge = node.querySelector(".message-badge");
            node.classList.toggle("has-unread", Boolean(unreadMessageCount));
            if (!unreadMessageCount) {
                if (badge) badge.remove();
                return;
            }
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "message-badge";
                node.appendChild(badge);
            }
            badge.textContent = unreadMessageCount > 9 ? "9+" : String(unreadMessageCount);
        });
        updatePageTitle();
    }

    function updateRealtimeStatus() {
        const alertsHead = document.querySelector("#alerts-panel .drawer-head h3");
        if (!alertsHead) return;
        let status = alertsHead.querySelector(".realtime-status");
        if (!status) {
            status = document.createElement("small");
            status.className = "realtime-status";
            alertsHead.appendChild(status);
        }
        status.textContent = unreadNotificationCount ? `새 알림 ${unreadNotificationCount}` : "실시간 확인 중";
    }

    function updatePageTitle() {
        const totalUnread = Number(unreadNotificationCount || 0) + Number(unreadMessageCount || 0);
        document.title = totalUnread ? `(${totalUnread}) ${baseTitle}` : baseTitle;
    }

    async function loadNotifications({ sinceId = null, markRead = false, silent = false } = {}) {
        const params = new URLSearchParams();
        if (sinceId !== null) params.set("since_id", String(sinceId));

        try {
            const response = await fetch(`/api/notifications${params.toString() ? `?${params}` : ""}`, {
                method: markRead ? "POST" : "GET",
            });
            const data = await response.json();
            if (!response.ok) {
                if (!silent) showToast(data.error || "알림을 불러오지 못했어요.");
                return;
            }

            const incoming = data.notifications || [];
            if (sinceId !== null) {
                const realIncoming = incoming.filter((item) => item.id > 0);
                if (realIncoming.length) {
                    notifications = [...realIncoming, ...notifications].slice(0, 20);
                    realIncoming.slice().reverse().forEach(showNotificationToast);
                }
            } else {
                notifications = incoming;
            }

            lastNotificationId = Math.max(lastNotificationId, data.latest_id || 0, ...notifications.map((item) => item.id || 0));
            unreadNotificationCount = markRead ? 0 : data.unread_count || 0;
            unreadMessageCount = data.message_unread_count ?? unreadMessageCount;
            renderNotifications();
            updateNotificationBadges();
            updateMessageBadges();
        } catch (error) {
            if (!silent) showToast("알림을 불러오지 못했어요.");
        }
    }

    function highlightPostFromHash() {
        if (!window.location.hash || !window.location.hash.startsWith("#post-")) return;
        const target = document.querySelector(window.location.hash);
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("post-highlight");
        window.setTimeout(() => target.classList.remove("post-highlight"), 2200);
    }

    function postIdFromHash(hash) {
        const match = String(hash || "").match(/^#post-(\d+)$/);
        return match ? match[1] : "";
    }

    function openPostFromHash(hash) {
        const postId = postIdFromHash(hash);
        if (!postId) return false;
        highlightPostFromHash();
        openPostDetail(postId);
        return true;
    }

    function initDeepLinks() {
        document.addEventListener("click", (event) => {
            const link = event.target.closest(".notification-item a, .drawer-item a, .notification-toast");
            if (!link) return;
            const url = new URL(link.href, window.location.origin);
            if (url.origin !== window.location.origin || !url.hash.startsWith("#post-")) return;

            if (page !== "home" || window.location.pathname !== "/") return;
            event.preventDefault();
            closePanel("alerts");
            window.location.hash = url.hash;
            openPostFromHash(url.hash);
        });

        window.addEventListener("hashchange", () => openPostFromHash(window.location.hash));
        window.setTimeout(() => openPostFromHash(window.location.hash), 200);
    }

    function initDrawerRefresh() {
        renderNotifications();
        updateNotificationBadges();
        updateMessageBadges();
        if (notificationRefreshTimer) window.clearInterval(notificationRefreshTimer);
        notificationRefreshTimer = window.setInterval(() => {
            loadNotifications({ sinceId: lastNotificationId, silent: true });
        }, 5000);
    }

    initNav();
    initPersonaShareCard();
    initStudioMaker();
    initUploadForm();
    initPostActions();
    initSearch();
    initProfileForm();
    initMessages();
    initDeepLinks();
    initDrawerRefresh();
    initPendingCaptionPolling();
})();

