/*
 * 富文本渲染增强（客户端）
 * ---------------------------------------------------------------------------
 * 为阅读端补上博客支持、但 toast-ui / 后端 Python markdown 不认识的语法：
 *   1. 数学公式：$行内$ 与 $$块级$$  → KaTeX
 *   2. 提示框：  > [!NOTE] 等 GitHub 风格块引用 → 带图标的提示框
 *
 * 渲染是幂等的：重复调用不会重复处理已渲染过的节点，
 * 因此可以安全地在每次内容更新后调用。
 */

import renderMathInElement from "katex/dist/contrib/auto-render.mjs";
import "katex/dist/katex.min.css";

const KATEX_DELIMITERS = [
	{ left: "$$", right: "$$", display: true },
	{ left: "\\[", right: "\\]", display: true },
	{ left: "$", right: "$", display: false },
	{ left: "\\(", right: "\\)", display: false },
];

const CALLOUT_META = {
	note: { label: "注意", icon: "ℹ" },
	tip: { label: "提示", icon: "✦" },
	important: { label: "重要", icon: "❢" },
	warning: { label: "警告", icon: "⚠" },
	caution: { label: "危险", icon: "⛔" },
};

const MARKER_PATTERN = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i;

/** 把 `> [!NOTE]` 形式的块引用转成带标题的提示框 */
function renderCallouts(root) {
	const quotes = root.querySelectorAll("blockquote");

	quotes.forEach((quote) => {
		if (quote.dataset.moonbirdCallout === "done") {
			return;
		}

		const firstBlock = quote.firstElementChild;
		if (!firstBlock) {
			return;
		}

		// 标记可能落在段落开头，也可能独占一行后跟正文
		const text = firstBlock.textContent ?? "";
		const match = text.match(MARKER_PATTERN);
		if (!match) {
			return;
		}

		const kind = match[1].toLowerCase();
		const meta = CALLOUT_META[kind];
		if (!meta) {
			return;
		}

		// 去掉标记本身，保留其余正文
		const remainder = text.replace(MARKER_PATTERN, "").trim();
		if (remainder) {
			firstBlock.textContent = remainder;
		} else {
			firstBlock.remove();
		}

		const title = document.createElement("p");
		title.className = "moonbird-callout-title";
		title.textContent = `${meta.icon} ${meta.label}`;
		quote.insertBefore(title, quote.firstChild);

		quote.classList.add("moonbird-callout", `moonbird-callout-${kind}`);
		quote.dataset.moonbirdCallout = "done";
	});
}

/** 用 KaTeX 渲染公式；跳过代码块内的内容，避免误伤代码示例 */
function renderMath(root) {
	if (!root.querySelector("*")) {
		return;
	}

	try {
		renderMathInElement(root, {
			delimiters: KATEX_DELIMITERS,
			throwOnError: false,
			ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
		});
	} catch (error) {
		// 公式渲染失败不应影响正文阅读
		console.warn("[blog-prose] 数学公式渲染失败：", error);
	}
}

/**
 * 对容器内的富文本做一次增强渲染。
 * @param {HTMLElement | null | undefined} root
 */
export function enhanceRichContent(root) {
	if (!root) {
		return;
	}

	renderCallouts(root);
	renderMath(root);
}
