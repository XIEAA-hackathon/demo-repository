import { useState } from 'react'
import SectionHeading from '../common/SectionHeading'
import { faqItems } from '../../config/eventContent'
import { ChevronDown } from 'lucide-react'

export default function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <section className="py-20" aria-labelledby="faq-heading">
      <div className="container-page">
        <SectionHeading
          id="faq-heading"
          eyebrow="Still Curious"
          title="Frequently Asked"
          align="center"
        />

        <div className="mx-auto mt-12 max-w-3xl divide-y divide-white/10 rounded-xl border border-white/10 bg-surface/50">
          {faqItems.map((item, index) => {
            const isOpen = openIndex === index
            return (
              <div key={item.question}>
                <h3>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
                    aria-expanded={isOpen}
                    aria-controls={`faq-answer-${index}`}
                    onClick={() => setOpenIndex(isOpen ? null : index)}
                  >
                    <span className="font-display text-base font-semibold text-white">
                      {item.question}
                    </span>
                    <ChevronDown
                      aria-hidden="true"
                      className={`h-5 w-5 shrink-0 text-purple-neon transition-transform duration-200 ${
                        isOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </button>
                </h3>
                <div
                  id={`faq-answer-${index}`}
                  role="region"
                  hidden={!isOpen}
                  className="px-6 pb-5"
                >
                  <p className="text-sm leading-relaxed text-ink-muted">{item.answer}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}