use this latex code and replace the files inside of resume/ dir like \_header.tex, resume/sections/achievements.tex and so on, if that makes sense, so  
basiclly the folder has content broken down, the same content that is in my resume, we just need to extract correct blocks of tex code from my tex resume  
and paste it in correct files inside of "resume" dir, you can ignore the comments in the pasted tex file, but the rest is my resume  
also remember to use context at hand, bcz those details are not mine and you cannot just use them to show my achievements or profressional experience

```
%-------------------------
% Resume in Latex
% Author : Jake Gutierrez
% Based off of: https://github.com/sb2nov/resume
% License : MIT
%------------------------

\documentclass[letterpaper, 11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames, dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage{fontawesome5}
\usepackage[dvipsnames]{xcolor}
\usepackage{multicol}
\usepackage[dvipsnames]{xcolor}
% \hypersetup{
%     colorlinks=true,
%     linkcolor=blue,
%     filecolor=magenta,
%     urlcolor=blue,
%     }
\setlength{\multicolsep}{-3.0pt}
\setlength{\columnsep}{-1pt}
\input{glyphtounicode}

%----------FONT OPTIONS----------
% sans-serif
% \usepackage[sfdefault]{FiraSans}
% \usepackage[sfdefault]{roboto}
% \usepackage[sfdefault]{noto-sans}
% \usepackage[default]{sourcesanspro}

% serif
% \usepackage{CormorantGaramond}
% \usepackage{charter}

\pagestyle{fancy}
\fancyhf{} % clear all header and footer fields
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

% Adjust margins
\addtolength{\oddsidemargin}{-0.6in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1.19in}
\addtolength{\topmargin}{-.7in}
\addtolength{\textheight}{1.4in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

% Sections formatting
\titleformat{\section}{ \vspace{-4pt}\scshape\raggedright\large\bfseries }{}{0em}{}[
\color{black}
\titlerule
\vspace{-5pt}
]

% Ensure that generate pdf is machine readable/ATS parsable
\pdfgentounicode=1

%-------------------------
% Custom commands
\newcommand{\resumeItem}[1]{ \item\small{ {#1 \vspace{-2pt}} } }

\newcommand{\classesList}[4]{ \item\small{ {#1 #2 #3 \vspace{-2pt}} } }

\newcommand{\resumeSubheading}[4]{
\vspace{-2pt}
\item
\begin{tabular*}{1.0\textwidth}[t]{l@{\extracolsep{\fill}}r}
	\textbf{#1}       & \textbf{\small #2} \\
	\textit{\small#3} & \textit{\small #4} \\
\end{tabular*}
\vspace{-7pt}
}

\newcommand{\resumeSubSubheading}[2]{ \item
\begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
	\textit{\small#1} & \textit{\small #2} \\
\end{tabular*}
\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[1]{ \item
\begin{tabular*}{1.001\textwidth}{l@{\extracolsep{\fill}}r}
	\small#1\

\end{tabular*}
\vspace{-7pt}
}
\definecolor{internal_link}{rgb}{0.1, 0.14, 0.13}

\newcommand{\resumeSubItem}[1]{\resumeItem{#1}
\vspace{-4pt}}

\renewcommand{\labelitemi}{$\vcenter{\hbox{\tiny$\bullet$}}$}
\renewcommand{\labelitemii}{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.0in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}
\vspace{-5pt}}

%-------------------------------------------
%%%%%%  RESUME STARTS HERE  %%%%%%%%%%%%%%%%%%%%%%%%%%%%

\begin{document}

%----------HEADING----------
\begin{center}
	{\Huge \scshape Uzair Saiyed} \\
	\vspace{1pt}
	Gujarat, India \\
	\vspace{1pt}
	{\color{MidnightBlue}\href[pdfnewwindow=true]{mailto:justuzairsaiyed@gmail.com}{\raisebox{-0.1\height}{\faEnvelope}\ \underline{justuzairsaiyed@gmail.com}}}~
	{\color{MidnightBlue}\href[pdfnewwindow=true]{https://linktr.ee/JustUzair}{\raisebox{-0.1\height}{\faLink}\ \underline{Links}}}~
	{\color{MidnightBlue}\href[pdfnewwindow=true]{https://linkedin.com/in/0xJustUzair}{\raisebox{-0.1\height}{\faLinkedin}\ \underline{0xJustUzair}}}~
	{\color{MidnightBlue}\href[pdfnewwindow=true]{https://github.com/JustUzair}{\raisebox{-0.1\height}{\faGithub}\ \underline{JustUzair}}}~
	\vspace{-8pt}
\end{center}

%-----------SUMMARY-----------
\section{{\color{MidnightBlue}{Summary}}}
\begin{itemize}[leftmargin=0.15in, label={}]
	\small{\item{
	Full-stack engineer with \textbf{18+ months} of production experience building across \textbf{Next.js}, \textbf{Node.js}, \textbf{REST APIs}, and modern web infrastructure. Specializes in \textbf{AI-Native} and \textbf{Web3} development, shipping production-grade \textbf{dApps}, \textbf{smart contracts}, and \textbf{developer tooling} on \textbf{EVM} ecosystems. Experienced building \textbf{autonomous agents}, \textbf{LLM-RAG pipelines}, and \textbf{agentic workflows} that bridge decentralized protocols with intelligent automation. Security-conscious by design, with a background in \textbf{Web3 Security}.
	}}
\end{itemize}
\vspace{-15pt}

%-----------EXPERIENCE-----------
\section{{\color{MidnightBlue}{Experience}}}
\resumeSubHeadingListStart
\vspace{5pt}

% --- Contract Work ---
\resumeSubheading{DeFi Protocol - Contract Work (NDA) $|$ AI \& Web3 Developer}{Nov 2025 - Jan 2026}{Remote, USA}{}
\resumeItemListStart
\vspace{1pt}
\resumeItem{Co-engineered an \textbf{EIP-7540 async vault} in \textbf{Solidity} with \href{https://arbiscan.io/address/0x9E832AB95765d730FCFA1e646aaae875f2532D25}{\underline{\color{internal_link}\textbf{mainnet deployment on Arbitrum}}}, enabling permissioned execution for both human and AI agents via \textbf{MetaMask Delegation Toolkit}; contributed the core liquidity tracking model for deployed and undeployed vault positions that was adopted into the final implementation.}
\resumeItem{Authored a \textbf{custom GMX \texttt{createOrder} calldata generation script} from scratch as a workaround for a buggy internal on-chain-actions product, pairing raw calldata construction with the \textbf{GMX SDK} and \textbf{MetaMask delegation signatures} to enable fully permissioned trade execution from the vault.}
\resumeItem{Built and delivered a \textbf{vault-less GMX x Allora AI trading agent} in \textbf{TypeScript/LangGraph} as a standalone backend proof-of-concept, executing real-time longs and shorts on \textbf{Arbitrum} driven by \textbf{Allora network} price predictions; validated on \textbf{Tenderly mainnet fork} with zero reverts, delivered within \textbf{2 weeks} including learning \textbf{LangGraph} from scratch.}
\resumeItem{Developed agentic hire/fire interface via \textbf{CopilotKit}, enabling users to spawn, control, and terminate trading agents through natural language with on-chain settlement.}
\resumeItemListEnd

\vspace{1pt}

% --- BuildBear (REFRAMED) ---
\resumeSubheading{BuildBear Labs $|$ Web3 Developer and Solutions Engineer}{Jan 2025 - Nov 2025}{Remote, Singapore}{}
\vspace{1pt}
\resumeItemListStart

\resumeItem{Owned and maintained production \textbf{Next.js documentation platform} built with \textbf{Fumadocs}, migrating content from \textbf{Strapi} to \textbf{MDX React components}; shipped weekly updates alongside backend and frontend releases, implementing \textbf{Open Graph metadata} and \textbf{SEO optimization} to improve developer-facing discoverability.}

\resumeItem{Authored the reference \textbf{GitHub Actions CI/CD template} for Web3 protocol repos, enabling \textbf{fork-based and fuzz testing} against live contract state via \textbf{BuildBear} sandboxes; supported \textbf{Liquity} and \textbf{Consensys} teams in adopting the workflow into their infrastructure.}

\resumeItem{Engineered a \textbf{mainnet-synchronized Uniswap V2 pool simulation tool} for a client protocol fork, pulling live \textbf{Chainlink} price data via BuildBear plugins, then minting/burning pool liquidity to mirror mainnet state; bypassed EVM transfer restrictions on pool contracts by deploying a \textbf{self-destruct contract} to force-feed tokens to liquidity-pools, resolving a blocker no standard approach could address.}

\resumeItem{Built reference integration repos for \textbf{Batua} (passkey wallet), \textbf{x402 protocol}, and \textbf{Pimlico} paymasters with BuildBear; produced video walkthroughs for \href{https://www.buildbear.io/docs/tutorials/across-plugin-tutorial\#step-by-step-video-tutorial}{\underline{\color{internal_link}\textbf{Across}}}, \href{https://www.buildbear.io/docs/tutorials/lifi-plugin-tutorial\#step-by-step-video-tutorial}{\underline{\color{internal_link}\textbf{LI.FI}}}, and \href{https://www.buildbear.io/docs/tutorials/pimlico-paymaster\#step-by-step-video-tutorial}{\underline{\color{internal_link}\textbf{Pimlico}}} adopted as official plugin documentation; unblocked partner dev-cycles for bridge testing where no viable testnet existed, driving \textbf{50+ plugin adoptions within 30 days}.}
\vspace{-10pt}
\resumeItem{Performed \textbf{black-box testing} on pre-release features, surfacing edge-case failures and routing structured feedback to product, frontend, and backend teams.}

\resumeItemListEnd

\vspace{1pt}

% --- Nethermind ---
\resumeSubheading{Nethermind $|$ Smart Contract Auditor Intern}{Sept 2024 - Dec 2024}{Remote, United Kingdom}{}
\resumeItemListStart
\resumeItem{Conducted security reviews across \textbf{re-staking} protocols, \textbf{AA paymasters}, \textbf{bridges}, \textbf{governance} modules, and \textbf{proof-of-liquidity} mechanisms in \textbf{Solidity} and \textbf{Cairo}.}
\resumeItem{Reported critical vulnerabilities with actionable mitigations; contributed to private audit reports at leading Web3 security firm.}
\resumeItemListEnd

\vspace{1pt}

% --- Kyte Social ---
\resumeSubheading{Kyte Social $|$ Full Stack Web2 and Web3 Intern}{April 2024 - July 2024}{Remote, India}{}
\resumeItemListStart
\resumeItem{Integrated on-chain smart contracts with frontend using \textbf{Next.js}, \textbf{Wagmi}, \textbf{Viem}; synced blockchain and backend state via \textbf{MongoDB}.}
\resumeItem{Built user-facing NFT collection creator that \textbf{reduced deployment time by 90\%}, abstracting ERC721/ERC1155 Factory complexity behind intuitive form interface.}
\resumeItem{Developed and tested \textbf{Solidity} smart contracts with \textbf{Foundry} (unit, fuzz, invariant testing); implemented off-chain reward claims via \textbf{Node.js} signing.}
\resumeItemListEnd

\vspace{1pt}

%-----------PROJECTS-----------
\section{{\color{MidnightBlue}{Projects}}}
\vspace{-10pt}
\resumeSubHeadingListStart

% --- Tessera RAG Platform ---
\resumeProjectHeading
{\textbf{Tessera} $|$ {\color{blue}\href[pdfnewwindow=true]{https://tessera-rag-ai.vercel.app}{\underline{Live Demo}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://github.com/JustUzair/Tessera-RAG-AI}{\underline{Github}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://documenter.getpostman.com/view/20867739/2sBXihrYt8}{\underline{API Docs}}}}
\vspace{-5pt}
\resumeItemListStart
\resumeItem{\textit{\textbf{Next.js 16}, \textbf{Express}, \textbf{MongoDB Atlas}, \textbf{LangChain}, \textbf{Vector Search}, \textbf{Zod}, \textbf{Framer Motion}, \textbf{Spline}}}
\resumeItem{Built a \textbf{production RAG platform} where users upload documents, ask questions, and receive \textbf{citation-backed answers with zero hallucination}. Every response includes clickable source chunks proving where the answer originated.}
\resumeItem{Architected \textbf{constraint-based agent design}: LangChain agent forbidden from answering until invoking \texttt{kb\_search} tool. \textbf{Structured JSON via Zod} prevents model responses from violating schema. Eliminates hallucination at the system level, not prompt engineering.}
\resumeItem{Engineered \textbf{semantic embedding cache} via CacheBackedEmbeddings to MongoDB KV store: document re-upload drops from \textbf{2.31s to 421ms} (82\% reduction). Namespace-based deduplication eliminates wasted embedding API calls.}
\resumeItem{Frontend: 3D Spline hero, Framer Motion animations, drag-and-drop KB panel, conversation threading, paginated history, full dark mode. \textbf{Lighthouse: Performance 92, Accessibility 96, Best Practices 100, SEO 100}.}
\resumeItem{Deployed on Vercel with Postman API docs and Vitest test suite validating ingestion, querying, schema enforcement, and citation integrity.}
\resumeItemListEnd

\vspace{-10pt}

% --- AXIOM ---
\resumeProjectHeading
{\textbf{AXIOM} $|$ {\color{blue}\href[pdfnewwindow=true]{https://axiom-ai-justuzair.vercel.app}{\underline{Live Demo}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://axiom-lcel-backend-justuzair.vercel.app}{\underline{Backend}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://documenter.getpostman.com/view/20867739/2sBXcLgHZF}{\underline{API Docs}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://github.com/JustUzair/axiom-lcel-rag}{\underline{Github}}}}
\vspace{-5pt}
\resumeItemListStart
\resumeItem{\textit{\textbf{TypeScript}, \textbf{Next.js}, \textbf{Express}, \textbf{LangChain LCEL}, \textbf{LightRAG}, \textbf{Tavily}, \textbf{Spline}, \textbf{Vercel Serverless Functions}}}
\resumeItem{Engineered a dual-mode AI search engine with a deterministic router using \textbf{30+ regex patterns} across 8 intent categories (pricing, recency, comparisons, URLs, reviews, etc.) to eliminate unnecessary LLM calls.}
\resumeItem{Web pipeline scrapes and summarizes the \textbf{top 5 results} in parallel, with graceful snippet fallback; KB pipeline chunks documents with a \textbf{200-char overlap window}, embedded as \textbf{Light-RAG}, and returns confidence-scored answers with full source citations.}
\resumeItem{Covered both pipelines with a \textbf{Vitest} integration test suite validating ingestion, querying, \textbf{Zod} schema enforcement (400s on bad input), and citation integrity; deployed rate-limited \textbf{Express} backend on \textbf{Vercel Serverless}.}
\resumeItem{Built a polished \textbf{Next.js} frontend featuring a \textbf{Spline 3D} hero, mouse-tracked spotlight, ambient orb backgrounds, per-word answer streaming reveals, and scramble-on-mount text animations via \textbf{Framer Motion}.}
\resumeItemListEnd

\vspace{-10pt}
% --- Mintrrs ---
\resumeProjectHeading
{\textbf{Mintrrs} $|$ {\color{blue}\href[pdfnewwindow=true]{https://github.com/JustUzair/NFT-Generator}{\underline{Github}}} $|$ {\color{blue}\href[pdfnewwindow=true]{https://www.postman.com/justuzair/workspace/justuzair-ughsal-nft-gen-nextjs}{\underline{API Docs}}}}
\vspace{-5pt}
\resumeItemListStart
\resumeItem{\textit{\textbf{Next.js}, \textbf{TypeScript}, \textbf{Tailwind}, \textbf{Solidity}, \textbf{Foundry}, \textbf{Wagmi}, \textbf{Viem}, \textbf{IPFS}, \textbf{MongoDB}}}
\resumeItem{Designed and deployed a \textbf{Factory Pattern} smart contract system, \texttt{NFTCollectionFactory} deploys isolated \textbf{ERC1155} collection contracts per artist, with \textbf{OpenZeppelin} Pausable, Supply, and Ownable extensions; tested end-to-end with a \textbf{Foundry} test suite and Forge deploy scripts.}
\resumeItem{Implemented dual-payment minting in Solidity accepting \textbf{native ETH} or \textbf{ERC20 (USDC)} via \texttt{transferFrom}, with per-address holder dedup via nested mappings, \textbf{batch minting}, and an \textbf{owner revenue withdrawal} function.}
\resumeItem{Serverless \textbf{Next.js} API routes handle SVG layer combination, \textbf{hash-map-based} duplicate prevention, and algorithmic generation; automated \textbf{IPFS} pipeline via \textbf{Pinata} pins images and metadata as a directory with the collection URI written on-chain post-deploy.}
\resumeItemListEnd

\resumeSubHeadingListEnd
\vspace{-10pt}

%-----------TECHNICAL SKILLS-----------
\section{{\color{MidnightBlue}{Technical Skills}}}
\begin{itemize}[leftmargin=0.15in, label={}]
	\small{\item{
	\textbf{Languages:} \textit{TypeScript, Rust, Python, Golang} \\
	\textbf{Frontend:} \textit{Next.js, React, Tailwind} \\
	\textbf{Backend:} \textit{Node.js, Express, Axum} \\
	\textbf{AI and LLM:} \textit{LangChain, LangGraph, CopilotKit, RAG, Embeddings, VectorDB} \\
	\textbf{Web3:} \textit{Solidity, Foundry, Wagmi, Viem, Rust (Solana, Move), IPFS} \\
	\textbf{Infrastructure:} \textit{MongoDB, Docker, GitHub Actions, CI/CD, Vercel} \\
	}}
\end{itemize}
\vspace{-10pt}

%-----------CERTIFICATIONS-----------
\section{{\color{MidnightBlue}{Certifications}}}
\begin{itemize}[leftmargin=0.15in, label={}]
	\resumeItemListStart
	\resumeItem{
	\textbf{Ackee Blockchain Solana Bootcamp (Graduate)} \quad
	\href[pdfnewwindow=true]{https://github.com/JustUzair/ackee-solana-s7-bootcamp}{\color{blue}Graduation Repo} $|$
	\href[pdfnewwindow=true]{https://solscan.io/tx/5Qd3tXZGAdWKEcf3pb1YnRmC8CNEDhET6WWjkuLa7d1V1bRMp8M4trDtsGxMEudT5FGuUMP3cfYr9ujFPXPtoHd8}{\color{blue}Graduation Certificate}
	}
	\resumeItem{\textbf{Smart Contract Security and Auditing} on \textbf{Cyfrin} \quad \href[pdfnewwindow=true]{https://www.linkedin.com/in/0xjustuzair/details/certifications/}{\color{blue}View Certification}}
	\resumeItemListEnd
\end{itemize}

%-----------ACHIEVEMENTS-----------
\section{{\color{MidnightBlue}{Achievements}}}
\begin{itemize}[leftmargin=0.15in, label={}]
	\resumeItemListStart
	\resumeItem{
		\textbf{Fantom Q1 2023 Hackathon} $|$ 1st Place Winner. Built Pumpkin Index Protocol, a DeFi index creation platform on Fantom. \href[pdfnewwindow=true]{https://devpost.com/software/pumpkin-protocol}{\color{blue}View on Devpost}
	}
	\resumeItem{
		\textbf{Theta Network 2023 Hackathon} $|$ 1st Place Winner. Built ThetaFans, a decentralized creator platform with NFT-gated content and multi-tier subscriptions. \href[pdfnewwindow=true]{https://devpost.com/software/thetafans}{\color{blue}View on Devpost}
	}
	\resumeItem{\textbf{RektOff Solana Rust Security Cohort} $|$ Selected as 1 of 75 participants from 2100+ applicants.}
	\resumeItemListEnd
\end{itemize}

%-----------EDUCATION-----------
\section{{\color{MidnightBlue}{Education}}}
\resumeSubHeadingListStart
\resumeSubheading
{Sarvajanik College of Engineering and Technology}{June 2024}{Bachelor of Technology Computer Engineering (CGPA: 9.17)}{Gujarat, India}
\resumeSubHeadingListEnd

\end{document}

```
