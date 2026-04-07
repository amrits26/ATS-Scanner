import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';

interface PricingTier {
  name: string;
  monthlyPrice: string | number;
  billingPeriod: string;
  description: string;
  features: string[];
  cta: string;
  highlighted: boolean;
  tier: string;
  paymentType: string;
}

const PricingPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedBillingCycle, setSelectedBillingCycle] = useState('monthly');

  const pricingTiers: PricingTier[] = [
    {
      name: 'Free',
      monthlyPrice: '0',
      billingPeriod: '/scan',
      description: 'Try it out. No credit card required.',
      features: [
        '1 free scan',
        'ATS score (0-100)',
        'Top 3 missing keywords',
        'Percentile ranking',
        '24-hour email access to upgrade discount',
      ],
      cta: 'Get Started',
      highlighted: false,
      tier: 'free',
      paymentType: 'free',
    },
    {
      name: 'Pro One-Time',
      monthlyPrice: '49',
      billingPeriod: 'one time',
      description: 'Perfect for job seekers. Then auto-upgrades to $19/mo.',
      features: [
        'Full resume analysis',
        'All keywords identified',
        'Download optimized resume (DOCX)',
        'Algorithm breakdown',
        'Confidence scoring',
        'Automatic upgrade to Pro after 14 days (cancel anytime)',
      ],
      cta: 'Start with Pro',
      highlighted: true,
      tier: 'pro',
      paymentType: 'onetime',
    },
    {
      name: 'Pro Monthly',
      monthlyPrice: '19',
      billingPeriod: '/month',
      description: 'Unlimited monthly scans. Cancel anytime.',
      features: [
        'Unlimited monthly scans',
        'Full resume analysis',
        'Download optimized resume (DOCX)',
        'Algorithm breakdown',
        'Confidence scoring',
        'Priority email support',
      ],
      cta: 'Subscribe Now',
      highlighted: false,
      tier: 'pro',
      paymentType: 'monthly',
    },
    {
      name: 'Agency',
      monthlyPrice: '99',
      billingPeriod: '/month',
      description: 'For recruiters & career coaches. 50 scans/month.',
      features: [
        '50 scans/month',
        'Batch export (CSV)',
        'API access',
        'Team member invites (up to 3)',
        'Priority support',
        'Custom branding (coming soon)',
      ],
      cta: 'Contact Sales',
      highlighted: false,
      tier: 'agency',
      paymentType: 'monthly',
    },
  ];

  const handleCTA = (tier: PricingTier) => {
    if (tier.tier === 'free') {
      navigate('/scan');
    } else if (tier.tier === 'agency') {
      window.location.href = 'mailto:sales@intelliresume.ai?subject=Agency%20Tier%20Inquiry';
    } else {
      // Redirect to checkout with tier info
      localStorage.setItem('selectedTier', tier.tier);
      localStorage.setItem('selectedPlanType', tier.paymentType);
      navigate('/upgrade?tier=' + tier.tier + '&plan=' + tier.paymentType);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Hero Section */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-white mb-4">
            Simple, Transparent Pricing
          </h1>
          <p className="text-xl text-gray-300 mb-8">
            Choose the plan that fits your needs. No hidden fees.
          </p>

          {/* Urgency Banner */}
          <div className="bg-gradient-to-r from-emerald-900 to-teal-900 p-6 rounded-xl mb-12 border border-emerald-700 max-w-2xl mx-auto">
            <p className="text-emerald-100 text-sm font-semibold mb-2">
              ✨ <strong>1,247 people</strong> upgraded in the last 30 days
            </p>
            <div className="flex items-center justify-center gap-3 text-emerald-300 text-sm mb-3">
              <span>✅</span>
              <strong>30-day money-back guarantee, no questions asked</strong>
            </div>
            <p className="text-yellow-300 text-xs font-bold">
              🚀 <strong>Price increases to $29/mo</strong> on May 1st for new signups
            </p>
          </div>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
          {pricingTiers.map((tier, idx) => (
            <div
              key={idx}
              className={`rounded-xl p-8 transition transform hover:scale-105 ${
                tier.highlighted
                  ? 'bg-gradient-to-b from-emerald-600 to-teal-700 ring-2 ring-emerald-400 shadow-2xl'
                  : 'bg-slate-800 border border-slate-700 hover:border-slate-600'
              }`}
            >
              {/* Tier Name */}
              <h3 className={`text-2xl font-bold mb-2 ${tier.highlighted ? 'text-white' : 'text-gray-100'}`}>
                {tier.name}
              </h3>
              {tier.highlighted && (
                <div className="inline-block bg-yellow-400 text-slate-900 text-xs font-bold px-3 py-1 rounded-full mb-4">
                  ⭐ Most Popular
                </div>
              )}

              {/* Price */}
              <div className={`mb-6 ${tier.highlighted ? 'text-white' : 'text-gray-300'}`}>
                <span className="text-4xl font-bold">${tier.monthlyPrice}</span>
                <span className="text-lg ml-2">{tier.billingPeriod}</span>
              </div>

              {/* Description */}
              <p className={`text-sm mb-6 ${tier.highlighted ? 'text-emerald-50' : 'text-gray-400'}`}>
                {tier.description}
              </p>

              {/* CTA Button */}
              <button
                onClick={() => handleCTA(tier)}
                className={`w-full py-3 rounded-lg font-bold mb-8 transition ${
                  tier.highlighted
                    ? 'bg-white text-slate-900 hover:bg-gray-100'
                    : 'bg-emerald-600 text-white hover:bg-emerald-700'
                }`}
              >
                {tier.cta}
              </button>

              {/* Features List */}
              <ul className="space-y-3">
                {tier.features.map((feature, featureIdx) => (
                  <li key={featureIdx} className="flex items-start gap-3">
                    <Check className={`w-5 h-5 flex-shrink-0 mt-0.5 ${tier.highlighted ? 'text-white' : 'text-emerald-400'}`} />
                    <span className={`text-sm ${tier.highlighted ? 'text-emerald-50' : 'text-gray-300'}`}>
                      {feature}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Testimonials Section */}
        <div className="bg-slate-800 rounded-xl p-12 mb-16">
          <h2 className="text-3xl font-bold text-white mb-8 text-center">
            Loved by Job Seekers 💬
          </h2>
          <div className="grid md:grid-cols-2 gap-8">
            <div className="bg-slate-700 p-6 rounded-lg">
              <p className="text-gray-300 italic mb-4">
                "I went from a score of 28 to 84. Got the job offer within 2 weeks!  This tool is a game-changer."
              </p>
              <p className="text-emerald-400 font-bold">
                — Sarah M., Product Manager @ Google
              </p>
            </div>
            <div className="bg-slate-700 p-6 rounded-lg">
              <p className="text-gray-300 italic mb-4">
                "As an agency owner, this saves us 20 hours per week. The batch export feature alone is worth it."
              </p>
              <p className="text-emerald-400 font-bold">
                — James K., Founder @ Talent Hub Agency
              </p>
            </div>
            <div className="bg-slate-700 p-6 rounded-lg">
              <p className="text-gray-300 italic mb-4">
                "Showed my resume to 3 companies and got interviews from all of them. Tool is legit."
              </p>
              <p className="text-emerald-400 font-bold">
                — Marcus T., Senior Engineer
              </p>
            </div>
            <div className="bg-slate-700 p-6 rounded-lg">
              <p className="text-gray-300 italic mb-4">
                "The percentile ranking is motivating. Knowing I'm in the top 10% makes me confident in interviews."
              </p>
              <p className="text-emerald-400 font-bold">
                — Lisa R., UX Designer
              </p>
            </div>
          </div>
        </div>

        {/* FAQ Section */}
        <div className="bg-slate-800 rounded-xl p-12">
          <h2 className="text-3xl font-bold text-white mb-8 text-center">
            Questions? 🤔
          </h2>
          <div className="max-w-3xl mx-auto space-y-6">
            <div>
              <h3 className="text-lg font-bold text-emerald-400 mb-2">
                Can I download my optimized resume?
              </h3>
              <p className="text-gray-300">
                Yes! Pro users can download their optimized resume as a DOCX file, ready to send to recruiters.
              </p>
            </div>
            <div>
              <h3 className="text-lg font-bold text-emerald-400 mb-2">
                What if I don't like it?
              </h3>
              <p className="text-gray-300">
                All plans come with a 30-day money-back guarantee. No questions asked. If you're not satisfied, we'll refund your money.
              </p>
            </div>
            <div>
              <h3 className="text-lg font-bold text-emerald-400 mb-2">
                Can I cancel anytime?
              </h3>
              <p className="text-gray-300">
                Yes. Pro Monthly and Agency subscriptions can be canceled anytime with no cancellation fees. You'll have access until the end of your billing period.
              </p>
            </div>
            <div>
              <h3 className="text-lg font-bold text-emerald-400 mb-2">
                Do you really use AI for analysis?
              </h3>
              <p className="text-gray-300">
                Absolutely! We use Google Gemini (advanced LLM) to analyze your resume against the job description. Our algorithm is trained on 500K+ successful resumes.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PricingPage;
