const CONFIG = {
    scrollSpeed: 40.0,
    fetchInterval: 10000,
    spotlightInterval: 60000,
    apiEndpoint: '/api/items',
    viewportId: 'viewport',
    trackId: 'track'
};
const MAX_LOOP_ITEMS = 100;

const CATEGORY_DISPLAY_LABELS = {
    threat_intel: "Threat Intel",
    research_analysis: "Research & Analysis",
    cloud_status: "Cloud Status",
    product_releases: "Product Releases",
    regulation_compliance: "Regulation & Compliance",
    internal: "Internal",
    uncategorized: "Uncategorized",
};

function getCategoryDisplayLabel(categoryKey) {
    return CATEGORY_DISPLAY_LABELS[categoryKey] ?? categoryKey;
}

// Helper functions needed for the initial fetch must also be outside the listener.
function getKey(item) {
    return item?.id ?? item?.guid ?? item?.link ?? `${item?.title}|${item?.link}`;
}

function calculatePriorityScore(item) {
    const now = new Date();
    const publishedDate = new Date(item.published);
    if (isNaN(publishedDate.getTime())) {
        return 0;
    }
    const hoursOld = (now - publishedDate) / (1000 * 60 * 60);
    const timeModifier = Math.pow(0.95, hoursOld);
    return item.criticality * timeModifier;
}

function buildTop100Snapshot(data) {
    const seen = new Set();
    const list = [];
    for (const raw of data) {
        const key = getKey(raw);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        const ts = Date.parse(raw.published || raw.pubDate || raw.date || "");
        list.push({ ...raw, __ts: isNaN(ts) ? 0 : ts });
    }
    list.sort((a, b) => b.__ts - a.__ts);
    const snapshot = list.slice(0, MAX_LOOP_ITEMS).map(({ __ts, ...rest }) => rest);
    return snapshot;
}

async function getInitialNewsData() {
    try {
        const response = await fetch(CONFIG.apiEndpoint);
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
            const topMain = data
                .map(item => ({ ...item, priorityScore: calculatePriorityScore(item) }))
                .sort((a, b) => b.priorityScore - a.priorityScore)
                .slice(0, 15);
            const snapshot = buildTop100Snapshot(data);
            return { topMain, snapshot, rawData: data };
        }
        return null;
    } catch (error) {
        console.error("News Feed: Failed to fetch initial items.", error);
        return null;
    }
}

const initialNewsPromise = getInitialNewsData();


document.addEventListener('DOMContentLoaded', () => {
        const track = document.getElementById(CONFIG.trackId);
        const fullscreenOverlay = document.getElementById('fullscreen-image-overlay');
        const FULLSCREEN_VISIBLE_MS = 45000;
        const FULLSCREEN_CYCLE_MS = 300000;
        let fullscreenHideTimer = null;
        let fullscreenShowTimer = null;
        let fullscreenVisible = false;

        function showFullscreenImage() {
            if (!fullscreenOverlay) return;
            if (fullscreenHideTimer) {
                clearTimeout(fullscreenHideTimer);
                fullscreenHideTimer = null;
            }
            if (fullscreenShowTimer) {
                clearTimeout(fullscreenShowTimer);
                fullscreenShowTimer = null;
            }
            fullscreenOverlay.classList.add('active');
            fullscreenVisible = true;
            fullscreenShowTimer = setTimeout(showFullscreenImage, FULLSCREEN_CYCLE_MS);
            fullscreenHideTimer = setTimeout(hideFullscreenImage, FULLSCREEN_VISIBLE_MS);
        }

        function hideFullscreenImage() {
            if (!fullscreenOverlay) return;
            if (fullscreenHideTimer) {
                clearTimeout(fullscreenHideTimer);
                fullscreenHideTimer = null;
            }
            fullscreenOverlay.classList.remove('active');
            fullscreenVisible = false;
        }

        showFullscreenImage();

        if (fullscreenOverlay) {
            fullscreenOverlay.addEventListener('click', hideFullscreenImage);
        }
    const viewport = document.getElementById(CONFIG.viewportId);
    const itemTemplate = document.getElementById('scroller-item-template');
    const clockElements = Array.from(document.querySelectorAll('[data-time-zone]'));
    const clockFormatters = new Map(clockElements.map(element => [
        element,
        new Intl.DateTimeFormat('en-GB', {
            timeZone: element.dataset.timeZone,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        })
    ]));
    const mainPanel = document.getElementById("main-news");
    const mainTitleEl = document.getElementById("main-news-title");
    const mainTitleDot = document.getElementById("main-criticality-dot");
    const mainSummaryEl = document.getElementById("main-news-summary");
    const mainCategoriesEl = document.getElementById("main-news-categories");
    const mainSourceEl = document.getElementById("main-news-source");
    const mainDateEl = document.getElementById("main-news-date");
    const mainFaviconElement = document.getElementById("main-news-favicon");
    const mainLinkEl = document.getElementById('main-news-link');
    const mainImageContainerEl = document.getElementById("main-news-image");
    const mainNewsTimerEl = document.getElementById('main-news-timer');
    const mainNewsTimerRingEl = document.getElementById('main-news-timer-ring');
    const TIMER_RADIUS = 8; // matches r="8" in the SVG circle
    const TIMER_CIRCUMFERENCE = 2 * Math.PI * TIMER_RADIUS;

    if (!track || !viewport || !itemTemplate) {
        console.error("News Feed Error: HTML elements not found.");
        return;
    }

    let currentOffset = 0;
    let isFetching = false;
    let isPaused = false;
    let ring = [];
    let pendingRing = null;
    let scrollerIndex = 0;
    let currentTopMain = [];
    let pendingTopMain = null;
    let currentMainIndex = 0;
    let initialRenderComplete = false;
    let fullDataCache = [];
    let allCategories = [];
    let activeCategories = new Set();
    let currentMainImageUrl = null;
    let touchScrollActive = false;
    let lastTouchY = null;

    if (mainTitleDot) {
        mainTitleDot.setAttribute('aria-label', 'Severity indicator');
    }
    let mainImageEl = null;
    if (mainImageContainerEl) {
        mainImageContainerEl.style.display = "none";
        mainImageEl = document.createElement("img");
        mainImageEl.loading = "eager";
        mainImageEl.decoding = "async";
        mainImageEl.className = "rounded-lg w-auto h-auto max-h-32 md:max-h-64 object-contain";
        mainImageEl.onload = () => {
            if (!mainImageContainerEl) return;
            if (mainImageEl.currentSrc !== currentMainImageUrl) return;
            mainImageContainerEl.style.display = "flex";
        };
        mainImageEl.onerror = () => {
            if (!mainImageContainerEl) return;
            if (mainImageEl.currentSrc !== currentMainImageUrl) return;
            mainImageContainerEl.style.display = "none";
        };
        mainImageContainerEl.innerHTML = '';
        mainImageContainerEl.appendChild(mainImageEl);
    }
    if (viewport) {
        const isTouchDevice = window.matchMedia("(pointer: coarse)").matches;
        if (!isTouchDevice) {
            viewport.addEventListener('mouseenter', () => {
                isPaused = true;
            });
            viewport.addEventListener('mouseleave', () => {
                isPaused = false;
            });
            viewport.addEventListener('wheel', (event) => {
                if (ring.length === 0) return;
                // Transform-based list needs explicit wheel handling for manual navigation.
                event.preventDefault();
                // Ensure no transition for immediate, smooth wheel scrolling
                track.style.transition = 'none';
                currentOffset -= event.deltaY;
                normalizeTrackWindow();
                track.style.transform = `translateY(${currentOffset}px)`;
            }, { passive: false });
        } else {
            viewport.addEventListener('touchstart', (event) => {
                if (ring.length === 0 || event.touches.length !== 1) return;
                touchScrollActive = true;
                isPaused = true;
                lastTouchY = event.touches[0].clientY;
            }, { passive: true });
            viewport.addEventListener('touchmove', (event) => {
                if (!touchScrollActive || ring.length === 0 || event.touches.length !== 1) return;
                const touchY = event.touches[0].clientY;
                const deltaY = touchY - lastTouchY;
                lastTouchY = touchY;
                event.preventDefault();
                currentOffset += deltaY;
                normalizeTrackWindow();
                track.style.transform = `translateY(${currentOffset}px)`;
            }, { passive: false });
            viewport.addEventListener('touchend', () => {
                touchScrollActive = false;
                lastTouchY = null;
                isPaused = false;
            });
            viewport.addEventListener('touchcancel', () => {
                touchScrollActive = false;
                lastTouchY = null;
                isPaused = false;
            });
        }
    }
    const htmlDecoder = document.createElement("textarea");
    const htmlStripper = document.createElement("div");

    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), delay);
        };
    }
    function recalculateItemHeights() {
        for (const item of track.children) {
            item.__cachedHeight = item.offsetHeight;
        }
    }
    const debouncedRecalculate = debounce(recalculateItemHeights, 250);
    window.addEventListener('resize', debouncedRecalculate);

    function simplifyUrl(urlString) {
        if (!urlString) {
            return '';
        }
        try {
            const hostname = new URL(urlString).hostname;
            return hostname.replace(/^www\./, '');
        } catch (error) {
            console.warn(`Could not simplify invalid URL: ${urlString}`);
            return '';
        }
    }

    function formatDate(dateString) {
        const date = new Date(dateString);
        const options = { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'};
        return date.toLocaleString('en-GB', options);
    }

    function getCriticalityColor(criticality) {
        if (criticality >= 100) return "bg-purple-600/60";
        if (criticality >= 80) return "bg-rose-700/60";
        if (criticality >= 50) return "bg-amber-500/60";
        return "bg-teal-600/60";
    }

    function getFaviconUrl(urlString) {
        if (!urlString) {
            return null;
        }
        try {
            const hostname = new URL(urlString).hostname;
            return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
        } catch (error) {
            console.warn(`Could not get favicon for invalid URL: ${urlString}`);
            return null;
        }
    }

    function ringsEqual(a, b) {
        if (!a || !b || a.length !== b.length) return false;
        for (let i = 0; i < a.length; i++) {
            if (getKey(a[i]) !== getKey(b[i])) return false;
        }
        return true;
    }

    function decodeHTML(html) {
        htmlDecoder.innerHTML = html ?? "";
        return htmlDecoder.value;
    }

    function stripAllHTML(encodedHtml) {
        const decoded = decodeHTML(encodedHtml);
        htmlStripper.innerHTML = decoded;
        return htmlStripper.textContent || htmlStripper.innerText || "";
    }

    function getItemDayKey(item) {
        const d = new Date(item.published || item.pubDate || item.date || 0);
        if (isNaN(d.getTime())) return '';
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }

    function formatDayLabel(item) {
        const d = new Date(item.published || item.pubDate || item.date || 0);
        if (isNaN(d.getTime())) return '';
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        if (d.getDate() === today.getDate() && d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear()) return 'Today';
        if (d.getDate() === yesterday.getDate() && d.getMonth() === yesterday.getMonth() && d.getFullYear() === yesterday.getFullYear()) return 'Yesterday';
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' });
    }

    function createDateDivider(item) {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex items-center gap-3 py-2.5 px-4';

        const lineLeft = document.createElement('div');
        lineLeft.className = 'flex-1 h-px bg-gradient-to-r from-transparent to-gray-200';

        const label = document.createElement('span');
        label.className = 'text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap';
        label.textContent = formatDayLabel(item);

        const lineRight = document.createElement('div');
        lineRight.className = 'flex-1 h-px bg-gradient-to-l from-transparent to-gray-200';

        wrapper.appendChild(lineLeft);
        wrapper.appendChild(label);
        wrapper.appendChild(lineRight);
        return wrapper;
    }

    function needsDayDividerAfterPrev(ringIndex) {
        if (ring.length <= 1) return false;
        const prevIndex = (ringIndex - 1 + ring.length) % ring.length;
        return getItemDayKey(ring[ringIndex]) !== getItemDayKey(ring[prevIndex]);
    }

    const burgerBtn = document.getElementById('burger-btn');
    const categoryMenu = document.getElementById('category-menu');
    const categoryListEl = document.getElementById('category-list');
    const selectAllBtn = document.getElementById('category-select-all');

    if (burgerBtn && categoryMenu) {
        burgerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            categoryMenu.classList.toggle('hidden');
        });
        document.addEventListener('click', (e) => {
            if (!categoryMenu.contains(e.target) && e.target !== burgerBtn) {
                categoryMenu.classList.add('hidden');
            }
        });
    }

    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            activeCategories = new Set(allCategories);
            renderCategoryCheckboxes();
            applyFilter();
        });
    }

    // Fetch the full category list from sources table — once on startup
    async function fetchCategories() {
        try {
            const response = await fetch('/api/categories');
            const data = await response.json();
            if (Array.isArray(data) && data.length > 0) {
                allCategories = data;
                activeCategories = new Set(allCategories);
                renderCategoryCheckboxes();
            }
        } catch (error) {
            console.error("Failed to fetch categories:", error);
        }
    }

    function renderCategoryCheckboxes() {
        if (!categoryListEl) return;
        categoryListEl.innerHTML = '';

        allCategories.forEach(cat => {
            const li = document.createElement('li');
            const label = document.createElement('label');
            label.className =
                'flex items-center gap-2 px-3 py-1.5 cursor-pointer ' +
                'hover:bg-gray-50 transition-colors text-sm text-gray-700';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = activeCategories.has(cat);
            checkbox.className = 'rounded';
            checkbox.addEventListener('change', () => {
                if (checkbox.checked) {
                    activeCategories.add(cat);
                } else {
                    activeCategories.delete(cat);
                }
                applyFilter();
            });

            const text = document.createElement('span');
            text.textContent = getCategoryDisplayLabel(cat);

            label.appendChild(checkbox);
            label.appendChild(text);
            li.appendChild(label);
            categoryListEl.appendChild(li);
        });
    }

    function getItemCategories(item) {
        if (!Array.isArray(item.categories) || item.categories.length === 0) {
            return ['uncategorized'];
        }
        return item.categories;
    }

    function filterItems(items) {
        if (activeCategories.size === allCategories.length) {
            return items;
        }
        return items.filter(item => {
            const cats = getItemCategories(item);
            return cats.some(c => activeCategories.has(c));
        });
    }

    function setMainNewsTimerVisibility(isVisible) {
        const display = isVisible ? '' : 'none';
        if (mainNewsTimerRingEl) {
            mainNewsTimerRingEl.style.display = display;
        } else if (mainNewsTimerEl) {
            mainNewsTimerEl.style.display = display;
        }
    }

    function applyFilter() {
        const filtered = filterItems(fullDataCache);

        const topMain = filtered
            .map(item => ({ ...item, priorityScore: calculatePriorityScore(item) }))
            .sort((a, b) => b.priorityScore - a.priorityScore)
            .slice(0, 15);

        currentTopMain = topMain;
        pendingTopMain = null;
        currentMainIndex = 0;

        if (currentTopMain.length > 0) {
            setMainNewsTimerVisibility(true);
            renderMainNews(currentTopMain[0]);
        } else {
            setMainNewsTimerVisibility(false);
            if (mainTitleEl) mainTitleEl.textContent = "No items match selected categories";
            if (mainCategoriesEl) mainCategoriesEl.innerHTML = '';
            if (mainSummaryEl) mainSummaryEl.textContent = "";
            if (mainTitleDot) mainTitleDot.style.display = 'none';
            if (mainSourceEl) mainSourceEl.textContent = "";
            if (mainDateEl) mainDateEl.textContent = "";
            if (mainFaviconElement) mainFaviconElement.style.display = 'none';
            if (mainLinkEl) mainLinkEl.removeAttribute('href');
            renderMainImage(null);
        }
        renderPriorityList(currentTopMain);

        ring = buildTop100Snapshot(filtered);
        scrollerIndex = 0;
        pendingRing = null;

        while (track.firstChild) track.removeChild(track.firstChild);
        currentOffset = 0;
        track.style.transform = 'translateY(0px)';
        fillScreen();
    }

    async function fetchNewsUpdates() {
        if (isFetching) return;
        isFetching = true;
        try {
            const response = await fetch(CONFIG.apiEndpoint);
            const data = await response.json();
            if (Array.isArray(data) && data.length > 0) {
                fullDataCache = data;

                const filtered = filterItems(data);

                const topMain = filtered
                    .map(item => ({ ...item, priorityScore: calculatePriorityScore(item) }))
                    .sort((a, b) => b.priorityScore - a.priorityScore)
                    .slice(0, 15);
                pendingTopMain = topMain;
                if (initialRenderComplete) {
                    renderPriorityList(topMain);
                }
                const snapshot = buildTop100Snapshot(filtered);
                if (!ringsEqual(ring, snapshot)) {
                    pendingRing = snapshot;
                }
            }
        } catch (error) {
            console.error("News Feed: Failed to fetch updates.", error);
        } finally {
            isFetching = false;
        }
    }

    function renderMainImage(imageUrl) {
        if (!mainImageEl || !mainImageContainerEl) return;
        currentMainImageUrl = imageUrl || null;
        mainImageContainerEl.style.display = "none";
        if (!imageUrl) {
            mainImageEl.removeAttribute("src");
        } else {
            mainImageEl.src = imageUrl;
        }
    }

    function renderMainNews(item) {
        if (!item) return;
        if (mainPanel) mainPanel.style.opacity = 0;
        setTimeout(() => {
            if (mainTitleEl && mainTitleDot) {
                mainTitleEl.textContent = item.title || 'No Title';
                mainTitleDot.className = `inline-block h-2 w-2 rounded-full flex-shrink-0 self-center ${getCriticalityColor(item.criticality)}`;
                mainTitleDot.setAttribute('title', `Criticality: ${item.criticality ?? 0}`);
                mainTitleDot.style.display = 'inline-block';
            }
            if (mainCategoriesEl) {
                mainCategoriesEl.innerHTML = '';
                const categories = getItemCategories(item);
                categories.forEach(cat => {
                    const badge = document.createElement('span');
                    badge.textContent = getCategoryDisplayLabel(cat);
                    badge.className = 'px-2 py-0.5 text-[11px] font-medium bg-gray-100 text-gray-700 rounded';
                    mainCategoriesEl.appendChild(badge);
                });
            }
            if (mainSummaryEl) mainSummaryEl.textContent = stripAllHTML(item.summary || '');
            if (mainLinkEl) {
                if (item.link) {
                    mainLinkEl.href = item.link;
                    mainLinkEl.target = '_blank';
                    mainLinkEl.rel = 'noopener';
                } else {
                    mainLinkEl.removeAttribute('href');
                }
            }

            if (mainSourceEl) {
                if (item.link) {
                    mainSourceEl.textContent = simplifyUrl(item.link)
                }
            }

            if (mainDateEl) {
                if (item.published) {
                    mainDateEl.textContent = formatDate(item.published);
                }
            }



            if (mainFaviconElement) {
                const mainFaviconUrl = getFaviconUrl(item.link);
                if (mainFaviconUrl) {
                    mainFaviconElement.src = mainFaviconUrl;
                    mainFaviconElement.onerror = () => {
                        mainFaviconElement.style.display = 'none';
                    };
                } else {
                    // If we can't even generate a URL (e.g., invalid link), hide it immediately.
                    mainFaviconElement.style.display = 'none';
                }
            }



            renderMainImage(item.image_url);
            if (mainPanel) mainPanel.style.opacity = 1;
        }, 200);
    }

    function advanceMainNews() {
        if (!currentTopMain || currentTopMain.length === 0) {
            const hasFilter = activeCategories.size < allCategories.length;
            if (mainTitleEl) mainTitleEl.textContent = hasFilter
                ? "No items match selected categories"
                : "No critical items";
            if (mainCategoriesEl) mainCategoriesEl.innerHTML = '';
            if (mainSummaryEl) mainSummaryEl.textContent = "";
            if (mainTitleDot) mainTitleDot.style.display = 'none';
            if (mainSourceEl) mainSourceEl.textContent = "";
            if (mainDateEl) mainDateEl.textContent = "";
            if (mainFaviconElement) mainFaviconElement.style.display = 'none';
            if (mainLinkEl) mainLinkEl.removeAttribute('href');
            setMainNewsTimerVisibility(false);
            renderMainImage(null);
            return;
        }
        setMainNewsTimerVisibility(true);
        const nextIndex = (currentMainIndex + 1) % currentTopMain.length;
        if (nextIndex === 0 && pendingTopMain && pendingTopMain.length > 0) {
            currentTopMain = pendingTopMain;
            pendingTopMain = null;
        }
        renderMainNews(currentTopMain[currentMainIndex]);
        currentMainIndex = nextIndex;
    }

    function createItemElement(item) {
        const itemFragment = itemTemplate.content.cloneNode(true);
        const linkElement = itemFragment.querySelector("a");
        const dotElement = itemFragment.querySelector(".scroller-item-dot");
        const titleElement = itemFragment.querySelector(".scroller-item-title");
        const dateElement = itemFragment.querySelector(".scroller-item-date");
        const sourceElement = itemFragment.querySelector(".scroller-item-source");
        const faviconElement = itemFragment.querySelector(".scroller-item-favicon")

        linkElement.href = item.link;

        const categories = getItemCategories(item);
        titleElement.textContent = "";
        const badgeContainer = document.createElement("div");
        badgeContainer.className = "flex gap-1 mr-1 flex-wrap items-center";

        categories.forEach(cat => {
            const badge = document.createElement("span");
            badge.textContent = getCategoryDisplayLabel(cat);
            badge.className = "px-1 py-1 text-[12px] bg-gray-100 text-gray-700 rounded";
            badgeContainer.appendChild(badge);
        });

        titleElement.appendChild(badgeContainer);
        titleElement.append(item.title || "No Title");
        
        dateElement.textContent = formatDate(item.published);
        if (sourceElement) {
            sourceElement.textContent = simplifyUrl(item.link);
        }


        if (faviconElement) {
            const faviconUrl = getFaviconUrl(item.link);
            if (faviconUrl) {
                faviconElement.src = faviconUrl;
                // If the favicon fails to load, hide it.
                faviconElement.onerror = () => {
                    faviconElement.style.display = 'none';
                };
            } else {
                // If we can't even generate a URL (e.g., invalid link), hide it immediately.
                faviconElement.style.display = 'none';
            }
        }

        dotElement.classList.add(getCriticalityColor(item.criticality));
        linkElement.__item = item;
        return linkElement;

    }

    function appendNextItem() {
        if (ring.length === 0) return;
        if (scrollerIndex === 0 && pendingRing && pendingRing.length > 0) {
            ring = pendingRing;
            pendingRing = null;
            scrollerIndex = 0;
        }
        const itemIndex = scrollerIndex;
        const item = ring[itemIndex];
        scrollerIndex = (scrollerIndex + 1) % ring.length;
        const linkEl = createItemElement(item);

        let el;
        if (needsDayDividerAfterPrev(itemIndex)) {
            // Make bottom border transparent on last item of previous day (divider handles separation)
            const prevChild = track.lastElementChild;
            if (prevChild) {
                const prevLink = prevChild.tagName === 'A' ? prevChild : prevChild.querySelector('a');
                if (prevLink) {
                    prevLink.classList.remove('border-gray-100');
                    prevLink.classList.add('border-transparent');
                }
            }
            el = document.createElement('div');
            el.appendChild(createDateDivider(item));
            el.appendChild(linkEl);
        } else {
            el = linkEl;
        }

        el.__ringIndex = itemIndex;
        track.appendChild(el);
        el.__cachedHeight = el.offsetHeight;
    }

    function prependPreviousItem() {
        if (ring.length === 0) return null;
        const firstItem = track.firstElementChild;
        const firstIndex = Number.isInteger(firstItem?.__ringIndex)
            ? firstItem.__ringIndex
            : scrollerIndex;
        const previousIndex = (firstIndex - 1 + ring.length) % ring.length;
        const linkEl = createItemElement(ring[previousIndex]);

        let el;
        if (needsDayDividerAfterPrev(previousIndex)) {
            el = document.createElement('div');
            el.appendChild(createDateDivider(ring[previousIndex]));
            el.appendChild(linkEl);
        } else {
            el = linkEl;
        }

        // If the prepended item is the last of its day (item below is a different day),
        // make border transparent since the divider handles the separation
        if (firstItem && Number.isInteger(firstIndex) &&
            getItemDayKey(ring[previousIndex]) !== getItemDayKey(ring[firstIndex])) {
            linkEl.classList.remove('border-gray-100');
            linkEl.classList.add('border-transparent');
        }

        el.__ringIndex = previousIndex;
        track.prepend(el);
        el.__cachedHeight = el.offsetHeight;
        return el;
    }

    function normalizeTrackWindow() {
        let firstItem = track.firstElementChild;
        let firstHeight = firstItem ? firstItem.__cachedHeight : 0;

        while (firstHeight && -currentOffset > firstHeight) {
            const nodeToRemove = track.firstElementChild;
            if (!nodeToRemove) break;

            track.removeChild(nodeToRemove);
            currentOffset += firstHeight;
            appendNextItem();

            firstItem = track.firstElementChild;
            firstHeight = firstItem ? firstItem.__cachedHeight : 0;
        }

        while (currentOffset > 0 && ring.length > 0) {
            const prepended = prependPreviousItem();
            if (!prepended) break;
            currentOffset -= prepended.__cachedHeight;

            const tail = track.lastElementChild;
            if (tail) {
                const tailIndex = tail.__ringIndex;
                track.removeChild(tail);
                if (Number.isInteger(tailIndex)) {
                    scrollerIndex = tailIndex;
                }
            }
        }
    }
    const priorityListEl = document.getElementById('priority-list');
    const priorityPanelEl = document.getElementById('priority-panel');
    const storyColumnEl = document.querySelector('.story-column');

    let lastPriorityCount = 0;

    function getPriorityItemCount() {
        const h = storyColumnEl ? storyColumnEl.clientHeight : document.documentElement.clientHeight;
        if (h >= 900) return 5;
        if (h >= 700) return 3;
        return 1;
    }

    if (storyColumnEl) {
        new ResizeObserver(() => {
            const newCount = getPriorityItemCount();
            if (newCount !== lastPriorityCount && currentTopMain && currentTopMain.length > 0) {
                renderPriorityList(currentTopMain);
            }
        }).observe(storyColumnEl);
    }

    function renderPriorityList(items) {
        if (!priorityListEl || !priorityPanelEl) return;
        if (!items || items.length === 0) {
            priorityPanelEl.style.display = "none";
            return;
        }
        priorityPanelEl.style.display = '';

        lastPriorityCount = getPriorityItemCount();
        const priorityItems = items.slice(0, lastPriorityCount);
        priorityListEl.innerHTML = '';

        priorityItems.forEach((item, index) => {
            const li = document.createElement('li');
            li.className = 'group';

            const a = document.createElement('a');
            a.href = item.link || '#';
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            a.className =
                'flex items-start gap-2.5 px-2.5 py-2 -mx-2.5 rounded-lg ' +
                'transition-colors duration-150 hover:bg-gray-50';

            const rank = document.createElement('span');
            rank.className =
                'flex-shrink-0 w-5 h-5 rounded-full text-[11px] font-bold ' +
                'flex items-center justify-center mt-0.5 ' +
                'bg-gray-100 text-gray-500 group-hover:bg-gray-200';
            rank.textContent = index + 1;

            const textBlock = document.createElement('div');
            textBlock.className = 'min-w-0 flex-1';

            const titleRow = document.createElement('div');
            titleRow.className = 'flex items-center gap-1.5';

            const dot = document.createElement('span');
            dot.className =
                `inline-block h-1.5 w-1.5 rounded-full flex-shrink-0 ${getCriticalityColor(item.criticality)}`;

            const title = document.createElement('span');
            title.className = 'text-sm font-medium text-gray-800 truncate';
            title.textContent = item.title || 'No Title';

            titleRow.appendChild(dot);
            titleRow.appendChild(title);

            const metaRow = document.createElement('div');
            metaRow.className = 'flex items-center gap-2 mt-0.5';

            const favicon = document.createElement('img');
            favicon.className = 'h-3 w-3 flex-shrink-0';
            const faviconUrl = getFaviconUrl(item.link);
            if (faviconUrl) {
                favicon.src = faviconUrl;
                favicon.onerror = () => { favicon.style.display = 'none'; };
            } else {
                favicon.style.display = 'none';
            }

            const source = document.createElement('span');
            source.className = 'text-xs text-gray-400 truncate';
            source.textContent = simplifyUrl(item.link);

            const sep = document.createElement('span');
            sep.className = 'text-xs text-gray-300';
            sep.textContent = '·';

            const timeAgo = document.createElement('span');
            timeAgo.className = 'text-xs text-gray-400 whitespace-nowrap flex-shrink-0';
            timeAgo.textContent = getTimeAgo(item.published);

            metaRow.appendChild(favicon);
            metaRow.appendChild(source);
            metaRow.appendChild(sep);
            metaRow.appendChild(timeAgo);

            textBlock.appendChild(titleRow);
            textBlock.appendChild(metaRow);

            a.appendChild(rank);
            a.appendChild(textBlock);
            li.appendChild(a);
            priorityListEl.appendChild(li);
        });
    }

    function getTimeAgo(dateString) {
        const now = new Date();
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return '';

        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;

        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;

        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
    }

    function fillScreen() {
        let guard = 0;
        while (ring.length > 0 && track.offsetHeight < viewport.offsetHeight * 2 && guard < 1000) {
            appendNextItem();
            guard++;
        }
    }

    let lastClockUpdate = 0;
    let lastNewsAdvance = 0;
    let lastFrameTime = 0;

    function updateWorldClocks() {
        const now = new Date();
        clockFormatters.forEach((formatter, element) => {
            element.textContent = formatter.format(now);
            element.dateTime = now.toISOString();
        });
    }

    updateWorldClocks();

    function animate(timestamp) {
        if (!lastFrameTime) lastFrameTime = timestamp;
        if (!lastClockUpdate) lastClockUpdate = timestamp;
        if (!lastNewsAdvance) lastNewsAdvance = timestamp;
        const deltaTime = timestamp - lastFrameTime;
        lastFrameTime = timestamp;
        if (timestamp - lastClockUpdate > 1000) {
            lastClockUpdate = timestamp;
            updateWorldClocks();
        }
        if (mainNewsTimerEl && lastNewsAdvance) {
            const elapsed = timestamp - lastNewsAdvance;
            const remaining = Math.max(0, 1 - elapsed / CONFIG.spotlightInterval);
            mainNewsTimerEl.setAttribute('stroke-dashoffset', TIMER_CIRCUMFERENCE * (1 - remaining));
        }
        if (timestamp - lastNewsAdvance > CONFIG.spotlightInterval) {
            lastNewsAdvance = timestamp;
            advanceMainNews();
        }
        if (!isPaused) {
            const scrollAmount = CONFIG.scrollSpeed * (deltaTime / 1000);
            currentOffset -= scrollAmount;
            normalizeTrackWindow();
            track.style.transform = `translateY(${currentOffset}px)`;
        }

        requestAnimationFrame(animate);
    }

    initialNewsPromise.then(async initialData => {
        if (initialData) {
            fullDataCache = initialData.rawData;

            currentTopMain = initialData.topMain;
            currentMainIndex = currentTopMain.length > 1 ? 1 : 0;
            renderMainNews(currentTopMain[0]);
            renderPriorityList(currentTopMain);
            ring = initialData.snapshot;
            scrollerIndex = 0;
            fillScreen();
        }
        initialRenderComplete = true;
        await fetchCategories();
        requestAnimationFrame(animate);
        setInterval(fetchNewsUpdates, CONFIG.fetchInterval);
    });

    const jumpToTopBtn = document.getElementById('jump-to-top');
    if (jumpToTopBtn) {
        jumpToTopBtn.addEventListener('click', () => {
            if (pendingRing && pendingRing.length > 0) {
                ring = pendingRing;
                pendingRing = null;
            }

            scrollerIndex = 0;

            while (track.firstChild) {
                track.removeChild(track.firstChild);
            }

            currentOffset = 0;
            track.style.transform = 'translateY(0px)';

            fillScreen();
        });
    }
    const SPEED_MAP = {
        slow:   15.0,
        medium: 25.0,
        fast:   40.0
    };

    const speedButtons = document.querySelectorAll('.speed-btn');
    const ACTIVE_CLASSES   = ['bg-gray-100', 'text-gray-800'];
    const INACTIVE_CLASSES = ['text-gray-400'];

    speedButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const speed = btn.dataset.speed;
            if (SPEED_MAP[speed] !== undefined) {
                CONFIG.scrollSpeed = SPEED_MAP[speed];
            }

            speedButtons.forEach(b => {
                b.classList.remove(...ACTIVE_CLASSES);
                b.classList.add(...INACTIVE_CLASSES);
            });
            btn.classList.remove(...INACTIVE_CLASSES);
            btn.classList.add(...ACTIVE_CLASSES);
        });
    });
});
