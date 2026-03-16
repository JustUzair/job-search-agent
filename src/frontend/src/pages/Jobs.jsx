import { useState } from "react";
import { tailorJob, getVariantPdfUrl, getVariantZipUrl } from "../api.js";
import QueueTab from "../components/QueueTab.jsx";
import AllResultsTab from "../components/AllResultsTab.jsx";

function PasteJobUrl() {
    const [url, setUrl] = useState("");
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [fitWarning, setFitWarning] = useState(null);

    const handleTailor = async (force = false) => {
        const shouldForce = force === true;
        if (!url.trim()) return;
        setLoading(true);
        setError(null);
        setResult(null);
        setFitWarning(null);
        try {
            const res = await tailorJob({
                url: url.trim(),
                force: shouldForce,
            });
            if (res.fit_warning) {
                setFitWarning(res);
            } else {
                setResult(res);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="mt-6 bg-slate-800 border border-slate-700 rounded-lg p-4">
            <div className="text-sm font-medium text-slate-300 mb-2">
                Paste a job URL to tailor directly
                <span className="ml-2 text-xs text-slate-500 font-normal">
                    Works with any job page — hiring.cafe, LinkedIn, Greenhouse,
                    etc.
                </span>
            </div>
            <div className="flex gap-2">
                <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleTailor()}
                    placeholder="https://hiring.cafe/job/..."
                    className="flex-1 bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500 placeholder-slate-500"
                />
                <button
                    onClick={() => handleTailor()}
                    disabled={loading || !url.trim()}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors whitespace-nowrap"
                >
                    {loading ? "⟳ Tailoring..." : "✍ Tailor"}
                </button>
            </div>

            {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

            {fitWarning && (
                <div className="mt-3 bg-amber-900/30 border border-amber-700 rounded p-3">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="text-amber-400">⚠</span>
                        <span className="text-amber-300 text-sm font-medium">
                            Poor fit — score {fitWarning.score}/100
                        </span>
                    </div>
                    <p className="text-amber-200 text-xs mb-2">
                        {fitWarning.reason}
                    </p>
                    <button
                        onClick={() => handleTailor(true)}
                        disabled={loading}
                        className="px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-60 text-white text-xs rounded font-medium transition-colors"
                    >
                        {loading ? "⟳ Tailoring..." : "Tailor anyway"}
                    </button>
                </div>
            )}

            {result && (
                <div className="mt-3 bg-slate-700/50 rounded p-3 text-sm">
                    <div className="text-emerald-400 font-medium mb-1">
                        ✓ Tailored for {result.company}
                    </div>
                    {result.changed_files?.length > 0 && (
                        <div className="text-xs text-slate-400 mb-2">
                            Changed: {result.changed_files.join(", ")}
                        </div>
                    )}
                    <div className="flex gap-2 flex-wrap">
                        {result.pdf_path ? (
                            <a
                                href={getVariantPdfUrl(result.variant_id || result.id)}
                                download
                                className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded font-medium transition-colors"
                            >
                                ↓ Download PDF
                            </a>
                        ) : result.compile_log ? (
                            <div className="relative group">
                                <span className="px-3 py-1.5 bg-red-900/40 text-red-300 text-xs rounded font-medium border border-red-800 cursor-help">
                                    ⚠ PDF Failed
                                </span>
                                <div className="absolute bottom-full mb-2 left-0 w-80 max-h-60 overflow-auto bg-slate-900 border border-slate-700 p-2 rounded text-[10px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity z-10 whitespace-pre-wrap">
                                    {result.compile_log}
                                </div>
                            </div>
                        ) : null}
                        {result.zip_path && (
                            <a
                                href={getVariantZipUrl(result.variant_id || result.id)}
                                download
                                className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-xs rounded font-medium transition-colors"
                            >
                                ↓ Download ZIP
                            </a>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default function Jobs() {
    const [activeTab, setActiveTab] = useState("queue");

    const tabCls = (t) =>
        `px-4 py-2 text-sm font-medium rounded-t transition-colors ${
            activeTab === t
                ? "bg-slate-800 text-white border-b-2 border-emerald-500"
                : "text-slate-400 hover:text-white"
        }`;

    return (
        <div>
            <div className="flex gap-1 mb-0 border-b border-slate-700">
                <button
                    className={tabCls("queue")}
                    onClick={() => setActiveTab("queue")}
                >
                    Queue
                </button>
                <button
                    className={tabCls("all")}
                    onClick={() => setActiveTab("all")}
                >
                    All Results
                </button>
            </div>

            <div className="bg-slate-800/30 rounded-b rounded-tr p-4 border border-slate-700 border-t-0">
                {activeTab === "queue" ? <QueueTab /> : <AllResultsTab />}
            </div>

            <PasteJobUrl />
        </div>
    );
}
