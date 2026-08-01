import { cx } from "@/lib/cva.config";
import { getProxyBaseUrl } from "../networking";
import { UiLoadingSpinner } from "../ui/ui-loading-spinner";

export default function LoadingScreen() {
  return (
    <div className={cx("h-screen", "flex items-center justify-center gap-4")}>
      <div className="py-2 pr-4 border-r border-r-gray-200">
        <img src={`${getProxyBaseUrl()}/get_image`} alt="XHub" className="h-8 w-auto max-w-[160px] object-contain" />
      </div>

      <div className="flex items-center justify-center gap-2">
        <UiLoadingSpinner className="size-4" />
        <span className="text-gray-600 text-sm">Loading...</span>
      </div>
    </div>
  );
}
