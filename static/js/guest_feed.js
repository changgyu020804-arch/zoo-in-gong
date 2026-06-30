(function () {
    const gate = document.getElementById("guest-gate-panel");
    const gateReason = document.getElementById("guest-gate-reason");
    const closeButton = document.getElementById("guest-gate-close");

    function openGate(reason) {
        if (!gate) return;
        if (gateReason) gateReason.textContent = reason || "이 기능을 사용하려면 로그인이 필요해요.";
        gate.classList.add("open");
        gate.setAttribute("aria-hidden", "false");
        document.body.classList.add("panel-open");
        closeButton?.focus();
    }

    function closeGate() {
        if (!gate) return;
        gate.classList.remove("open");
        gate.setAttribute("aria-hidden", "true");
        document.body.classList.remove("panel-open");
    }

    function icon(className) {
        const element = document.createElement("i");
        element.className = className;
        return element;
    }

    function gateButton(className, label, reason, children) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `${className} js-guest-gate`;
        button.dataset.gateReason = reason;
        button.setAttribute("aria-label", label);
        children.forEach((child) => button.append(child));
        return button;
    }

    function reactionCount(className, label, reason, iconNode, count) {
        const value = document.createElement("strong");
        value.textContent = String(count || 0);
        return gateButton(`dog-action-button ${className}`, label, reason, [iconNode, value]);
    }

    function createGuestPost(post) {
        const article = document.createElement("article");
        article.className = "post-card dog-social-card guest-post-card";
        article.id = `post-${post.id}`;

        const header = document.createElement("div");
        header.className = "post-header";
        const author = gateButton(
            "post-author guest-profile-button",
            `${post.pet_name || "강아지"} 프로필`,
            `${post.pet_name || "이 친구"}의 프로필을 보려면 로그인이 필요해요.`,
            [],
        );
        const avatar = document.createElement("span");
        avatar.className = "avatar avatar-small avatar-ring";
        if (post.display_avatar_url) {
            const avatarImage = document.createElement("img");
            avatarImage.src = post.display_avatar_url;
            avatarImage.alt = post.pet_name || "강아지";
            avatar.appendChild(avatarImage);
        } else {
            const initial = document.createElement("span");
            initial.textContent = post.initial || (post.pet_name || "멍").slice(0, 1);
            avatar.appendChild(initial);
        }
        const authorCopy = document.createElement("span");
        authorCopy.className = "guest-author-copy";
        const authorName = document.createElement("strong");
        authorName.textContent = post.pet_name || post.username || "멍스타";
        const authorMeta = document.createElement("span");
        authorMeta.className = "meta-line";
        authorMeta.textContent = `${post.time_label || "방금 전"} · ${post.persona || ""}`;
        authorCopy.append(authorName, authorMeta);
        author.append(avatar, authorCopy);

        const tools = document.createElement("div");
        tools.className = "post-header-tools";
        const follow = gateButton(
            "follow-button",
            "팔로우",
            `${post.pet_name || "이 친구"}를 팔로우하려면 로그인이 필요해요.`,
            [document.createTextNode("팔로우")],
        );
        const species = document.createElement("span");
        species.className = "tag-pill";
        species.textContent = post.pet_species || "강아지";
        tools.append(follow, species);
        header.append(author, tools);

        const imageWrap = document.createElement("div");
        imageWrap.className = "post-image-wrap guest-post-image";
        const image = document.createElement("img");
        image.className = "post-image";
        image.src = post.image_url || "";
        image.alt = `${post.pet_name || "강아지"} 사진`;
        image.loading = "lazy";
        image.decoding = "async";
        imageWrap.appendChild(image);

        const actions = document.createElement("div");
        actions.className = "post-actions dog-social-actions";
        const cuteEmoji = document.createElement("span");
        cuteEmoji.className = "reaction-emoji";
        cuteEmoji.setAttribute("aria-hidden", "true");
        cuteEmoji.textContent = "🥰";
        actions.append(
            reactionCount("", "좋아요", "좋아요를 남기려면 로그인이 필요해요.", icon("fa-solid fa-heart"), post.likes),
            reactionCount("reaction-button reaction-cute", "귀여워", "귀여워 반응을 남기려면 로그인이 필요해요.", cuteEmoji, post.cute_count),
            reactionCount("reaction-button reaction-funny", "웃겨", "웃겨 반응을 남기려면 로그인이 필요해요.", icon("fa-solid fa-face-laugh-squint"), post.funny_count),
            reactionCount("", "댓글", "댓글을 남기려면 로그인이 필요해요.", icon("fa-regular fa-comment"), post.comment_count),
        );
        const bookmark = gateButton(
            "icon-button save-button",
            "저장",
            "게시물을 저장하려면 로그인이 필요해요.",
            [icon("fa-regular fa-bookmark")],
        );
        actions.appendChild(bookmark);

        const copy = document.createElement("div");
        copy.className = "post-copy";
        const caption = document.createElement("p");
        caption.className = "caption";
        const captionName = document.createElement("strong");
        captionName.textContent = `${post.pet_name || "멍스타"}:`;
        const captionText = document.createElement("span");
        captionText.innerHTML = post.caption || "";
        caption.append(captionName, " ", captionText);
        copy.appendChild(caption);

        const commentPrompt = gateButton(
            "guest-comment-prompt",
            "댓글 작성",
            "댓글을 남기려면 로그인이 필요해요.",
            [icon("fa-regular fa-comment"), document.createTextNode("댓글을 남겨보세요")],
        );

        article.append(header, imageWrap, actions, copy, commentPrompt);
        return article;
    }

    async function loadMorePosts() {
        const pagination = document.getElementById("guest-feed-pagination");
        const button = document.getElementById("guest-feed-load-more");
        const feed = document.getElementById("guest-feed-list");
        const status = pagination?.querySelector(".feed-pagination-status");
        if (!pagination || !button || !feed || button.disabled) return;

        button.disabled = true;
        if (status) status.textContent = "게시물을 불러오는 중이에요.";
        const params = new URLSearchParams({ limit: "20" });
        if (pagination.dataset.beforeCreatedAt) params.set("before_created_at", pagination.dataset.beforeCreatedAt);
        if (pagination.dataset.beforeId) params.set("before_id", pagination.dataset.beforeId);

        try {
            const response = await fetch(`/api/feed?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "피드를 불러오지 못했어요.");
            (data.posts || []).forEach((post) => feed.appendChild(createGuestPost(post)));
            pagination.dataset.hasMore = data.has_more ? "true" : "false";
            pagination.dataset.beforeCreatedAt = data.next_cursor?.created_at || "";
            pagination.dataset.beforeId = data.next_cursor?.id || "";
            pagination.hidden = !data.has_more;
            if (status) status.textContent = data.has_more ? "" : "모든 게시물을 확인했어요.";
        } catch (error) {
            if (status) status.textContent = error.message || "피드를 불러오지 못했어요.";
        } finally {
            button.disabled = false;
        }
    }

    document.addEventListener("click", (event) => {
        const gated = event.target.closest(".js-guest-gate");
        if (gated) {
            event.preventDefault();
            openGate(gated.dataset.gateReason);
            return;
        }

        const rankingTab = event.target.closest(".js-guest-ranking-tab");
        if (rankingTab) {
            const mode = rankingTab.dataset.rankingTab;
            document.querySelectorAll(".js-guest-ranking-tab").forEach((button) => {
                const active = button.dataset.rankingTab === mode;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-selected", active ? "true" : "false");
            });
            document.querySelectorAll(".js-guest-ranking-panel").forEach((panel) => {
                panel.hidden = panel.dataset.rankingPanel !== mode;
            });
        }
    });

    closeButton?.addEventListener("click", closeGate);
    gate?.addEventListener("click", (event) => {
        if (event.target === gate) closeGate();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && gate?.classList.contains("open")) closeGate();
    });
    document.getElementById("guest-feed-load-more")?.addEventListener("click", loadMorePosts);

    const postHash = /^#post-(\d+)$/.exec(window.location.hash);
    if (postHash) document.getElementById(`post-${postHash[1]}`)?.scrollIntoView({ block: "center" });
})();
