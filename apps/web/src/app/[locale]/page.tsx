"use client";

import { useState, useEffect, useRef } from "react";
import { motion, useInView, useScroll, useTransform, AnimatePresence } from "framer-motion";
import {
  ArrowDown,
  ArrowRight,
  Coffee,
  FileText,
  GitMerge,
  Circle,
  Clock,
  TrendingUp,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Show, UserButton, SignInButton } from "@clerk/nextjs";
import LanguageSwitcher from "@/components/LanguageSwitcher";

// Animation variants
const fadeInUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.1,
    },
  },
};

// Coffee Cup Animation Component
function CoffeeCupAnimation({ show }: { show: boolean }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          className="inline-flex items-center justify-center ml-4"
        >
          <div className="relative">
            <Coffee className="w-10 h-10 text-green" />
            {/* Steam particles */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 flex gap-1">
              <div className="w-1 h-3 bg-green/30 rounded-full animate-steam steam-1" />
              <div className="w-1 h-3 bg-green/30 rounded-full animate-steam steam-2" />
              <div className="w-1 h-3 bg-green/30 rounded-full animate-steam steam-3" />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Navigation Component
function Navigation() {
  const t = useTranslations();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 100);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <motion.nav
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1] }}
      className={`fixed top-0 left-0 right-0 z-50 h-16 transition-all duration-300 ${
        scrolled
          ? "bg-cream/85 backdrop-blur-md border-b border-divider"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-full flex items-center justify-between">
        <div className="text-dark-green font-medium text-xl tracking-tight">
          {t('brand')}
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <Show when="signed-out">
            <SignInButton>
              <button className="bg-green hover:bg-green-dark text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
                {t('nav.signIn')}
              </button>
            </SignInButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </div>
    </motion.nav>
  );
}

// Hero Section
function HeroSection() {
  const t = useTranslations('hero');
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.3 });
  const [showStrikethrough, setShowStrikethrough] = useState(false);
  const [textRevealed, setTextRevealed] = useState(false);
  const [hideScrollHint, setHideScrollHint] = useState(false);

  useEffect(() => {
    if (isInView) {
      const timer1 = setTimeout(() => setShowStrikethrough(true), 800);
      const timer2 = setTimeout(() => setTextRevealed(true), 1200);
      return () => {
        clearTimeout(timer1);
        clearTimeout(timer2);
      };
    }
  }, [isInView]);

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 100) {
        setHideScrollHint(true);
      }
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <section
      ref={ref}
      className="min-h-screen bg-cream flex flex-col items-center justify-center relative px-6"
    >
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-4xl mx-auto text-center"
      >
        {/* Main Headline */}
        <motion.h1
          variants={fadeInUp}
          className="text-[clamp(2rem,6vw,4.5rem)] font-semibold leading-[1.2] text-charcoal mb-6"
        >
          <span className="block">{t('title.line1')}</span>
          <span className="block mt-2">
            {!textRevealed ? (
              <span className="relative inline-block">
                {t('title.line2Before')}
                <span className="relative mx-2 text-green">
                  {t('title.pdfStack')}
                  {showStrikethrough && (
                    <motion.span
                      initial={{ width: 0 }}
                      animate={{ width: "100%" }}
                      transition={{ duration: 0.3, ease: "easeOut" }}
                      className="absolute left-0 top-1/2 h-1 bg-green rounded-full"
                    />
                  )}
                </span>
                {t('title.start')}
              </span>
            ) : (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="inline-flex items-center flex-wrap justify-center gap-x-2"
              >
                {t('title.line2After')}
                <span className="text-ochre">{t('title.coffeeTime')}</span>
                {t('title.startEnd')}
                <CoffeeCupAnimation show={true} />
              </motion.span>
            )}
          </span>
        </motion.h1>

        {/* Subtitle */}
        <motion.div variants={staggerContainer} className="space-y-2 mb-12">
          <motion.p variants={fadeInUp} className="text-xl text-warm-gray">
            {t('subtitle')}
          </motion.p>
          <motion.p variants={fadeInUp} className="text-lg text-warm-gray/80">
            {t('description')}
          </motion.p>
        </motion.div>

        {/* CTA Button */}
        <motion.div
          variants={fadeInUp}
          className="flex items-center justify-center"
        >
          <SignInButton>
            <button className="group bg-green hover:bg-green-dark text-white px-8 py-4 rounded-xl text-base font-medium transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl flex items-center gap-2">
              {t('ctaPrimary')}
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </button>
          </SignInButton>
        </motion.div>
      </motion.div>

      {/* Scroll Indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: hideScrollHint ? 0 : 1 }}
        transition={{ delay: 2.2, duration: 0.6 }}
        className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
      >
        <span className="text-sm text-warm-gray">{t('scrollHint')}</span>
        <ArrowDown className="w-5 h-5 text-green animate-float" />
      </motion.div>
    </section>
  );
}

// Problem Statement Section
function ProblemSection() {
  const t = useTranslations('problem');
  const brandT = useTranslations();
  const containerRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  const phase = useTransform(scrollYProgress, [0, 0.25, 0.5, 0.75, 1], [0, 1, 2, 2, 2]);
  const [currentPhase, setCurrentPhase] = useState(0);

  useEffect(() => {
    const unsubscribe = phase.on("change", (v) => {
      setCurrentPhase(Math.min(Math.floor(v), 2));
    });
    return () => unsubscribe();
  }, [phase]);

  return (
    <section ref={containerRef} className="relative h-[300vh] bg-dark-green">
      <div className="sticky top-0 h-screen flex items-center justify-center px-6">
        <div className="max-w-4xl mx-auto text-center">
          <AnimatePresence mode="wait">
            {currentPhase <= 2 && (
              <motion.div
                key={currentPhase}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
                className="space-y-4"
              >
                {currentPhase === 0 && (
                  <>
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0 }}
                      className="text-[clamp(1.75rem,5vw,3.5rem)] font-medium text-white leading-tight"
                    >
                      {t('phase1.line1')}
                    </motion.p>
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.15 }}
                      className="text-[clamp(1.75rem,5vw,3.5rem)] font-medium text-white leading-tight"
                    >
                      {t('phase1.line2')}
                    </motion.p>
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.3 }}
                      className="text-[clamp(1.75rem,5vw,3.5rem)] font-medium text-white leading-tight"
                    >
                      {t('phase1.line3')}
                      <span className="text-gold">{t('phase1.highlight')}</span>
                      {t('phase1.line3End')}
                    </motion.p>
                  </>
                )}
                {currentPhase === 1 && (
                  <>
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0 }}
                      className="text-[clamp(1.75rem,5vw,3.5rem)] font-medium text-white leading-tight"
                    >
                      {t('phase2.line1')}
                    </motion.p>
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.15 }}
                      className="text-[clamp(1.75rem,5vw,3.5rem)] font-medium text-white leading-tight"
                    >
                      {t('phase2.line2')}
                      <span className="text-ochre animate-glow">{t('phase2.highlight')}</span>
                    </motion.p>
                  </>
                )}
                {currentPhase === 2 && (
                  <motion.p
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.5 }}
                    className="text-[clamp(2rem,6vw,4rem)] font-semibold text-white leading-tight"
                  >
                    {t('phase3.prefix')} {brandT('brand')} {t('phase3.suffix')}
                  </motion.p>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

// Dashboard Mock Component
function DashboardMock({ highlight }: { highlight?: string }) {
  const t = useTranslations('product.dashboard');
  const brandT = useTranslations();
  const brandName = brandT('brand');

  return (
    <div className="bg-white rounded-2xl shadow-2xl overflow-hidden border border-divider/50">
      {/* Browser Header */}
      <div className="bg-cream-light px-4 py-3 flex items-center gap-2 border-b border-divider/50">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-warm-gray/30" />
          <div className="w-3 h-3 rounded-full bg-warm-gray/30" />
          <div className="w-3 h-3 rounded-full bg-warm-gray/30" />
        </div>
        <div className="flex-1 text-center text-xs text-warm-gray/60 font-mono">
          app.{brandName.toLowerCase()}.com/dashboard
        </div>
      </div>

      {/* Dashboard Content */}
      <div className="p-6 bg-cream/50">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-charcoal">{t('title')}</h2>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-green/10 flex items-center justify-center">
              <span className="text-green text-xs font-medium">JL</span>
            </div>
          </div>
        </div>

        {/* Portfolio Snapshot Cards */}
        <div className={`grid grid-cols-4 gap-4 mb-6 transition-all duration-500 ${highlight === "snapshot" ? "opacity-100 ring-2 ring-green rounded-lg p-1" : highlight ? "opacity-40" : "opacity-100"}`}>
          {[
            { label: t('totalAum'), value: "¥ 234.5M" },
            { label: t('todaysPnL'), value: "+¥ 3.28M", sub: "(+1.42%)" },
            { label: t('netExposure'), value: "67.3%", sub: "Net Long" },
            { label: t('positions'), value: "47" },
          ].map((item, i) => (
            <div key={i} className="bg-white p-4 rounded-xl border border-divider/50">
              <p className="text-xs text-warm-gray mb-1">{item.label}</p>
              <p className={`text-lg font-semibold ${item.sub?.includes("+") ? "text-green" : "text-charcoal"}`}>
                {item.value}
              </p>
              {item.sub && <p className="text-xs text-warm-gray">{item.sub}</p>}
            </div>
          ))}
        </div>

        {/* Risk Status Bar */}
        <div className={`bg-white rounded-xl p-4 mb-6 border border-divider/50 transition-all duration-500 ${highlight === "risk" ? "opacity-100 ring-2 ring-green" : highlight ? "opacity-40" : "opacity-100"}`}>
          <div className="flex items-center gap-4">
            <span className="text-xs font-medium text-warm-gray">{t('riskStatus')}</span>
            <div className="h-4 w-px bg-divider" />
            <div className="flex gap-2">
              {["Liquidity Stress", "VaR Limit", "Sector Concentration", "Vol Spike Detection", "Leverage Ratio"].map((risk, i) => (
                <span
                  key={i}
                  className={`px-3 py-1 rounded-full text-xs ${
                    i < 3 ? "bg-green/10 text-green" : i === 3 ? "bg-gold/10 text-gold" : "bg-red-100 text-red-600"
                  }`}
                >
                  {risk}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Recommendations */}
        <div className={`transition-all duration-500 ${highlight === "recommendations" ? "opacity-100 ring-2 ring-green rounded-xl" : highlight ? "opacity-40" : "opacity-100"}`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-charcoal">
              {t('recommendations')}
              <span className="ml-2 text-sm text-warm-gray font-normal">· 5 total · 3 pending review</span>
            </h3>
            <span className="text-xs text-green font-medium">{t('viewAll')}</span>
          </div>

          <div className="space-y-3">
            {[
              { name: "Kweichow Moutai", code: "600519.SH", sector: "Consumer Staples · Premium Baijiu", action: "BUY", confidence: "HIGH", status: t('pendingReview'), trend: "up" },
              { name: "LONGi Green Energy", code: "601012.SH", sector: "Industrials · Solar Technology", action: "SELL", confidence: "MEDIUM", status: t('pendingReview'), trend: "down" },
            ].map((stock, i) => (
              <div key={i} className="bg-white rounded-xl p-4 flex items-center justify-between border border-divider/50">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${stock.trend === "up" ? "bg-red-50" : "bg-green/10"}`}>
                    <TrendingUp className={`w-5 h-5 ${stock.trend === "up" ? "text-red-500" : "text-green"}`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-charcoal">{stock.name}</span>
                      <span className="text-xs text-warm-gray bg-cream px-1.5 py-0.5 rounded">{stock.code}</span>
                    </div>
                    <p className="text-xs text-warm-gray italic">{stock.sector}</p>
                  </div>
                </div>
                <div className="flex items-center gap-8">
                  <div className="text-center">
                    <p className="text-xs text-warm-gray mb-0.5">{t('action')}</p>
                    <p className={`font-semibold ${stock.action === "BUY" ? "text-red-500" : "text-green"}`}>{stock.action}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-warm-gray mb-0.5">{t('confidence')}</p>
                    <p className="font-semibold text-charcoal">{stock.confidence}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-warm-gray mb-0.5">{t('status')}</p>
                    <span className="px-3 py-1 rounded-full text-xs bg-gold/10 text-gold border border-gold/20">
                      {stock.status}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// Product Reveal Section
function ProductSection() {
  const t = useTranslations('product');
  const containerRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  const phase = useTransform(scrollYProgress, [0, 0.2, 0.4, 0.6, 0.8, 1], [0, 1, 2, 3, 3, 3]);
  const [currentPhase, setCurrentPhase] = useState(0);

  useEffect(() => {
    const unsubscribe = phase.on("change", (v) => {
      setCurrentPhase(Math.min(Math.floor(v), 3));
    });
    return () => unsubscribe();
  }, [phase]);

  const phases = [
    { label: t('phases.0.label'), title: t('phases.0.title'), highlight: "snapshot" },
    { label: t('phases.1.label'), title: t('phases.1.title'), highlight: "risk" },
    { label: t('phases.2.label'), title: t('phases.2.title'), highlight: "recommendations" },
    { label: t('phases.3.label'), title: t('phases.3.title'), highlight: "full" },
  ];

  const descriptions = [
    t('phases.0.description'),
    t('phases.1.description'),
    t('phases.2.description'),
    t('phases.3.description'),
  ];

  return (
    <section ref={containerRef} id="product" className="relative h-[350vh] bg-cream">
      <div className="sticky top-0 h-screen flex items-center">
        <div className="w-full max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Left: Dashboard Mock */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, ease: [0.25, 0.1, 0.25, 1] }}
            viewport={{ once: true }}
            className="order-2 lg:order-1"
          >
            <DashboardMock highlight={phases[currentPhase].highlight === "full" ? undefined : phases[currentPhase].highlight} />
          </motion.div>

          {/* Right: Description */}
          <div className="order-1 lg:order-2 lg:pl-8">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentPhase}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
              >
                <span className="inline-block px-3 py-1 bg-green/10 text-green rounded-full text-sm font-medium mb-4">
                  {phases[currentPhase].label}
                </span>
                <h2 className="text-3xl md:text-4xl font-semibold text-charcoal mb-6 leading-tight">
                  {phases[currentPhase].title}
                </h2>
                <p className="text-lg text-warm-gray leading-relaxed">
                  {descriptions[currentPhase]}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}

// Feature Card Component
function FeatureCard({
  icon: Icon,
  titleKey,
  descriptionKey,
  delay,
}: {
  icon: React.ElementType;
  titleKey: string;
  descriptionKey: string;
  delay: number;
}) {
  const t = useTranslations('features');
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.1 });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 30 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay, ease: [0.25, 0.1, 0.25, 1] }}
      whileHover={{ y: -2, boxShadow: "0 8px 24px rgba(0,0,0,0.06)" }}
      className="bg-white rounded-2xl p-8 border border-divider/50 transition-shadow duration-200"
    >
      <div className="w-14 h-14 rounded-xl bg-green/10 flex items-center justify-center mb-5">
        <Icon className="w-7 h-7 text-green" />
      </div>
      <h3 className="text-xl font-semibold text-charcoal mb-3">{t(titleKey)}</h3>
      <p className="text-warm-gray leading-relaxed">{t(descriptionKey)}</p>
    </motion.div>
  );
}

// Features Section
function FeaturesSection() {
  const features = [
    { icon: FileText, titleKey: "cards.0.title", descriptionKey: "cards.0.description" },
    { icon: GitMerge, titleKey: "cards.1.title", descriptionKey: "cards.1.description" },
    { icon: Circle, titleKey: "cards.2.title", descriptionKey: "cards.2.description" },
  ];

  return (
    <section className="py-20 bg-cream px-6">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {features.map((feature, i) => (
            <FeatureCard key={i} {...feature} delay={i * 0.15} />
          ))}
        </div>
      </div>
    </section>
  );
}

// Workflow Section
function WorkflowSection() {
  const t = useTranslations('workflow');
  const containerRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  const phase = useTransform(scrollYProgress, [0, 0.15, 0.3, 0.45, 0.6, 0.75, 1], [0, 1, 2, 3, 4, 4, 4]);
  const [currentPhase, setCurrentPhase] = useState(0);

  useEffect(() => {
    const unsubscribe = phase.on("change", (v) => {
      setCurrentPhase(Math.min(Math.floor(v), 4));
    });
    return () => unsubscribe();
  }, [phase]);

  const timeline = [
    {
      time: t('timeline.0.time'),
      title: t('timeline.0.title'),
      content: t('timeline.0.content'),
      quote: t('timeline.0.quote'),
      action: t('timeline.0.action'),
    },
    {
      time: t('timeline.1.time'),
      title: t('timeline.1.title'),
      content: t('timeline.1.content'),
      quote: t('timeline.1.quote'),
      action: t('timeline.1.action'),
      highlight: true,
    },
    {
      time: t('timeline.2.time'),
      title: t('timeline.2.title'),
      content: t('timeline.2.content'),
      quote: t('timeline.2.quote'),
      action: t('timeline.2.action'),
      climax: true,
    },
    {
      time: t('timeline.3.time'),
      title: t('timeline.3.title'),
      content: t('timeline.3.content'),
      quote: t('timeline.3.quote'),
      action: t('timeline.3.action'),
    },
    {
      time: t('timeline.4.time'),
      title: t('timeline.4.title'),
      content: t('timeline.4.content'),
      quote: "",
      action: t('timeline.4.action'),
      ending: true,
    },
  ];

  return (
    <section ref={containerRef} className="relative h-[400vh] bg-dark-green">
      <div className="sticky top-0 h-screen overflow-hidden">
        <div className="max-w-4xl mx-auto px-6 h-full flex items-center">
          {/* Timeline */}
          <div className="relative shrink-0 w-8 self-stretch flex flex-col items-center py-[25vh]">
            <div className="absolute inset-y-[25vh] left-1/2 -translate-x-1/2 w-0.5 bg-white/20" />
            {timeline.map((_, i) => (
              <motion.div
                key={i}
                className={`absolute w-3 h-3 rounded-full left-1/2 -translate-x-1/2 transition-colors duration-300 ${
                  i <= currentPhase ? "bg-gold" : "bg-white/30"
                }`}
                style={{ top: `calc(25vh + ${(i / (timeline.length - 1)) * 50}vh)` }}
              />
            ))}
          </div>

          {/* Content */}
          <div className="ml-8 w-full max-w-2xl">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentPhase}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
                className="bg-white/5 border border-white/10 rounded-2xl p-8"
              >
                <div className="flex items-center gap-3 mb-6">
                  <Clock className="w-5 h-5 text-gold" />
                  <span className="text-gold font-medium">{timeline[currentPhase].time}</span>
                  <span className="text-white/40">—</span>
                  <span className="text-white font-medium">{timeline[currentPhase].title}</span>
                </div>

                <p className="text-cream-light/90 mb-4">{timeline[currentPhase].content}</p>

                {timeline[currentPhase].quote && (
                  <blockquote className="border-l-2 border-gold pl-4 my-6 text-cream-light/80 italic">
                    &ldquo;{timeline[currentPhase].quote}&rdquo;
                  </blockquote>
                )}

                {timeline[currentPhase].climax ? (
                  <p className="text-ochre text-2xl font-bold">{timeline[currentPhase].action}</p>
                ) : timeline[currentPhase].ending ? (
                  <p className="text-white text-3xl font-semibold text-center mt-8">{timeline[currentPhase].action}</p>
                ) : timeline[currentPhase].highlight ? (
                  <p className="text-gold text-xl font-semibold">{timeline[currentPhase].action}</p>
                ) : (
                  <p className="text-cream-light/70">{timeline[currentPhase].action}</p>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}

// Philosophy Section
function PhilosophySection() {
  const t = useTranslations('philosophy');
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  const beliefs = [
    { titleKey: "beliefs.0.title", contentKey: "beliefs.0.content" },
    { titleKey: "beliefs.1.title", contentKey: "beliefs.1.content" },
    { titleKey: "beliefs.2.title", contentKey: "beliefs.2.content" },
  ];

  return (
    <section ref={ref} className="py-20 bg-cream px-6">
      <div className="max-w-2xl mx-auto">
        <motion.p
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          className="text-center text-sm text-warm-gray tracking-[4px] uppercase mb-10"
        >
          {t('title')}
        </motion.p>

        <div className="space-y-12">
          {beliefs.map((belief, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              animate={isInView ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
              transition={{ delay: i * 0.2, duration: 0.6 }}
              className="text-center"
            >
              <h3 className="text-xl font-semibold text-green mb-4">{t(belief.titleKey)}</h3>
              <p className="text-charcoal/80 leading-[1.8] text-lg">{t(belief.contentKey)}</p>
              {i < beliefs.length - 1 && (
                <div className="w-10 h-px bg-divider mx-auto mt-12" />
              )}
            </motion.div>
          ))}
        </div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.8 }}
          className="text-center text-warm-gray mt-14 text-base"
        >
          {t('footer')}
        </motion.p>
      </div>
    </section>
  );
}

// CTA Section
function CTASection() {
  const t = useTranslations('cta');
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.3 });

  return (
    <section ref={ref} className="min-h-screen bg-dark-green flex flex-col items-center justify-center relative px-6 py-20">
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-3xl mx-auto text-center flex-1 flex flex-col items-center justify-center"
      >
        <motion.h2
          variants={fadeInUp}
          className="text-[clamp(2.5rem,6vw,4rem)] font-semibold text-white leading-tight mb-6"
        >
          {t('title.line1')}
          <br />
          <span className="text-gold">{t('title.line2')}</span>
        </motion.h2>

        <motion.p variants={fadeInUp} className="text-cream-light text-lg mb-10">
          {t('subtitle')}
        </motion.p>

        <motion.div variants={fadeInUp}>
          <SignInButton>
            <button className="group bg-white hover:bg-cream text-dark-green px-10 py-5 rounded-2xl text-lg font-medium transition-all duration-200 hover:-translate-y-1 hover:shadow-2xl hover:shadow-gold/20">
              {t('button')}
            </button>
          </SignInButton>
        </motion.div>

        <motion.p variants={fadeInUp} className="text-warm-gray/70 text-sm mt-6">
          {t('footer')}
        </motion.p>
      </motion.div>

      <motion.footer
        initial={{ opacity: 0 }}
        animate={isInView ? { opacity: 1 } : {}}
        transition={{ delay: 0.8 }}
        className="w-full text-center pt-8"
      >
        <p className="text-cream-light/50 text-sm">{t('copyright')}</p>
      </motion.footer>
    </section>
  );
}

// Main Page Component
export default function Home() {
  return (
    <main className="overflow-x-clip">
      <Navigation />
      <HeroSection />
      <ProblemSection />
      <ProductSection />
      <FeaturesSection />
      <WorkflowSection />
      <PhilosophySection />
      <CTASection />
    </main>
  );
}
