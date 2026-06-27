/* Adapted from
 * https://github.com/linux-rdma/rdma-core/blob/v42.7/ccan/check_type.h

 * Statement of Purpose
 * 
 * The laws of most jurisdictions throughout the world automatically confer
 * exclusive Copyright and Related Rights (defined below) upon the creator and
 * subsequent owner(s) (each and all, an "owner") of an original work of
 * authorship and/or a database (each, a "Work").
 * 
 * Certain owners wish to permanently relinquish those rights to a Work for the
 * purpose of contributing to a commons of creative, cultural and scientific works
 * ("Commons") that the public can reliably and without fear of later claims of
 * infringement build upon, modify, incorporate in other works, reuse and
 * redistribute as freely as possible in any form whatsoever and for any purposes,
 * including without limitation commercial purposes. These owners may contribute
 * to the Commons to promote the ideal of a free culture and the further
 * production of creative, cultural and scientific works, or to gain reputation or
 * greater distribution for their Work in part through the use and efforts of
 * others.
 * 
 * For these and/or other purposes and motivations, and without any expectation of
 * additional consideration or compensation, the person associating CC0 with a
 * Work (the "Affirmer"), to the extent that he or she is an owner of Copyright
 * and Related Rights in the Work, voluntarily elects to apply CC0 to the Work and
 * publicly distribute the Work under its terms, with knowledge of his or her
 * Copyright and Related Rights in the Work and the meaning and intended legal
 * effect of CC0 on those rights.
 * 
 * 1. Copyright and Related Rights. A Work made available under CC0 may be
 * protected by copyright and related or neighboring rights ("Copyright and
 * Related Rights"). Copyright and Related Rights include, but are not limited to,
 * the following:
 * 
 *     the right to reproduce, adapt, distribute, perform, display, communicate,
 * and translate a Work; moral rights retained by the original author(s) and/or
 * performer(s); publicity and privacy rights pertaining to a person's image or
 * likeness depicted in a Work; rights protecting against unfair competition in
 * regards to a Work, subject to the limitations in paragraph 4(a), below; rights
 * protecting the extraction, dissemination, use and reuse of data in a Work;
 * database rights (such as those arising under Directive 96/9/EC of the European
 * Parliament and of the Council of 11 March 1996 on the legal protection of
 * databases, and under any national implementation thereof, including any amended
 * or successor version of such directive); and other similar, equivalent or
 * corresponding rights throughout the world based on applicable law or treaty,
 * and any national implementations thereof.
 * 
 * 2. Waiver. To the greatest extent permitted by, but not in contravention of,
 * applicable law, Affirmer hereby overtly, fully, permanently, irrevocably and
 * unconditionally waives, abandons, and surrenders all of Affirmer's Copyright
 * and Related Rights and associated claims and causes of action, whether now
 * known or unknown (including existing as well as future claims and causes of
 * action), in the Work (i) in all territories worldwide, (ii) for the maximum
 * duration provided by applicable law or treaty (including future time
 * extensions), (iii) in any current or future medium and for any number of
 * copies, and (iv) for any purpose whatsoever, including without limitation
 * commercial, advertising or promotional purposes (the "Waiver"). Affirmer makes
 * the Waiver for the benefit of each member of the public at large and to the
 * detriment of Affirmer's heirs and successors, fully intending that such Waiver
 * shall not be subject to revocation, rescission, cancellation, termination, or
 * any other legal or equitable action to disrupt the quiet enjoyment of the Work
 * by the public as contemplated by Affirmer's express Statement of Purpose.
 * 
 * 3. Public License Fallback. Should any part of the Waiver for any reason be
 * judged legally invalid or ineffective under applicable law, then the Waiver
 * shall be preserved to the maximum extent permitted taking into account
 * Affirmer's express Statement of Purpose. In addition, to the extent the Waiver
 * is so judged Affirmer hereby grants to each affected person a royalty-free, non
 * transferable, non sublicensable, non exclusive, irrevocable and unconditional
 * license to exercise Affirmer's Copyright and Related Rights in the Work (i) in
 * all territories worldwide, (ii) for the maximum duration provided by applicable
 * law or treaty (including future time extensions), (iii) in any current or
 * future medium and for any number of copies, and (iv) for any purpose
 * whatsoever, including without limitation commercial, advertising or promotional
 * purposes (the "License"). The License shall be deemed effective as of the date
 * CC0 was applied by Affirmer to the Work. Should any part of the License for any
 * reason be judged legally invalid or ineffective under applicable law, such
 * partial invalidity or ineffectiveness shall not invalidate the remainder of the
 * License, and in such case Affirmer hereby affirms that he or she will not (i)
 * exercise any of his or her remaining Copyright and Related Rights in the Work
 * or (ii) assert any associated claims and causes of action with respect to the
 * Work, in either case contrary to Affirmer's express Statement of Purpose.
 * 
 * 4. Limitations and Disclaimers.
 * 
 *     No trademark or patent rights held by Affirmer are waived, abandoned,
 * surrendered, licensed or otherwise affected by this document.  Affirmer offers
 * the Work as-is and makes no representations or warranties of any kind
 * concerning the Work, express, implied, statutory or otherwise, including
 * without limitation warranties of title, merchantability, fitness for a
 * particular purpose, non infringement, or the absence of latent or other
 * defects, accuracy, or the present or absence of errors, whether or not
 * discoverable, all to the greatest extent permissible under applicable law.
 * Affirmer disclaims responsibility for clearing rights of other persons that may
 * apply to the Work or any use thereof, including without limitation any person's
 * Copyright and Related Rights in the Work. Further, Affirmer disclaims
 * responsibility for obtaining any necessary consents, permissions or other
 * rights required for any use of the Work.  Affirmer understands and acknowledges
 * that Creative Commons is not a party to this document and has no duty or
 * obligation with respect to this CC0 or use of the Work.
 */

#ifndef CCAN_CHECK_TYPE_H
#define CCAN_CHECK_TYPE_H
#include "config.h"

/**
 * check_type - issue a warning or build failure if type is not correct.
 * @expr: the expression whose type we should check (not evaluated).
 * @type: the exact type we expect the expression to be.
 *
 * This macro is usually used within other macros to try to ensure that a macro
 * argument is of the expected type.  No type promotion of the expression is
 * done: an unsigned int is not the same as an int!
 *
 * check_type() always evaluates to 0.
 *
 * If your compiler does not support typeof, then the best we can do is fail
 * to compile if the sizes of the types are unequal (a less complete check).
 *
 * Example:
 *	// They should always pass a 64-bit value to _set_some_value!
 *	#define set_some_value(expr)			\
 *		_set_some_value((check_type((expr), uint64_t), (expr)))
 */

/**
 * check_types_match - issue a warning or build failure if types are not same.
 * @expr1: the first expression (not evaluated).
 * @expr2: the second expression (not evaluated).
 *
 * This macro is usually used within other macros to try to ensure that
 * arguments are of identical types.  No type promotion of the expressions is
 * done: an unsigned int is not the same as an int!
 *
 * check_types_match() always evaluates to 0.
 *
 * If your compiler does not support typeof, then the best we can do is fail
 * to compile if the sizes of the types are unequal (a less complete check).
 *
 * Example:
 *	// Do subtraction to get to enclosing type, but make sure that
 *	// pointer is of correct type for that member.
 *	#define container_of(mbr_ptr, encl_type, mbr)			\
 *		(check_types_match((mbr_ptr), &((encl_type *)0)->mbr),	\
 *		 ((encl_type *)						\
 *		  ((char *)(mbr_ptr) - offsetof(enclosing_type, mbr))))
 */
#if HAVE_TYPEOF
#define check_type(expr, type)			\
	((typeof(expr) *)0 != (type *)0)

#define check_types_match(expr1, expr2)		\
	((typeof(expr1) *)0 != (typeof(expr2) *)0)
#else
#include <ccan/build_assert.h>
/* Without typeof, we can only test the sizes. */
#define check_type(expr, type)					\
	BUILD_ASSERT_OR_ZERO(sizeof(expr) == sizeof(type))

#define check_types_match(expr1, expr2)				\
	BUILD_ASSERT_OR_ZERO(sizeof(expr1) == sizeof(expr2))
#endif /* HAVE_TYPEOF */

#endif /* CCAN_CHECK_TYPE_H */
