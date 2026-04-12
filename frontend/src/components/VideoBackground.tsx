import { useIsMobile } from "@/hooks/use-mobile";

const VIDEO_VERSION = "20260326-hd";

const VideoBackground = () => {
  const isMobile = useIsMobile();
  const videoSrc = isMobile
    ? `/videos/hero-bg-mobile.mp4?v=${VIDEO_VERSION}`
    : `/videos/hero-bg-desktop.mp4?v=${VIDEO_VERSION}`;

  return (
    <>
      <video
        key={videoSrc}
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        className="fixed inset-0 w-full h-full object-cover z-0 [transform:translateZ(0)]"
        style={{
          imageRendering: "auto",
          WebkitBackfaceVisibility: "hidden",
          backfaceVisibility: "hidden",
        }}
        src={videoSrc}
      />
      <div className="fixed inset-0 bg-background/45 z-0" />
    </>
  );
};

export default VideoBackground;
