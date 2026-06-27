/* Adapted from
 * https://github.com/linux-rdma/rdma-core/blob/v42.7/ccan/container_of.h

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
#ifndef CCAN_CONTAINER_OF_H
#define CCAN_CONTAINER_OF_H
#include <stddef.h>

#include "config.h"
#include <ccan/check_type.h>

/**
 * container_of - get pointer to enclosing structure
 * @member_ptr: pointer to the structure member
 * @containing_type: the type this member is within
 * @member: the name of this member within the structure.
 *
 * Given a pointer to a member of a structure, this macro does pointer
 * subtraction to return the pointer to the enclosing type.
 *
 * Example:
 *	struct foo {
 *		int fielda, fieldb;
 *		// ...
 *	};
 *	struct info {
 *		int some_other_field;
 *		struct foo my_foo;
 *	};
 *
 *	static struct info *foo_to_info(struct foo *foo)
 *	{
 *		return container_of(foo, struct info, my_foo);
 *	}
 */
#ifndef container_of
#define container_of(member_ptr, containing_type, member)		\
	 ((containing_type *)						\
	  ((char *)(member_ptr)						\
	   - container_off(containing_type, member))			\
	  + check_types_match(*(member_ptr), ((containing_type *)0)->member))
#endif

/**
 * container_of_or_null - get pointer to enclosing structure, or NULL
 * @member_ptr: pointer to the structure member
 * @containing_type: the type this member is within
 * @member: the name of this member within the structure.
 *
 * Given a pointer to a member of a structure, this macro does pointer
 * subtraction to return the pointer to the enclosing type, unless it
 * is given NULL, in which case it also returns NULL.
 *
 * Example:
 *	struct foo {
 *		int fielda, fieldb;
 *		// ...
 *	};
 *	struct info {
 *		int some_other_field;
 *		struct foo my_foo;
 *	};
 *
 *	static struct info *foo_to_info_allowing_null(struct foo *foo)
 *	{
 *		return container_of_or_null(foo, struct info, my_foo);
 *	}
 */
static inline char *container_of_or_null_(void *member_ptr, size_t offset)
{
	return member_ptr ? (char *)member_ptr - offset : NULL;
}
#define container_of_or_null(member_ptr, containing_type, member)	\
	((containing_type *)						\
	 container_of_or_null_(member_ptr,				\
			       container_off(containing_type, member))	\
	 + check_types_match(*(member_ptr), ((containing_type *)0)->member))

/**
 * container_off - get offset to enclosing structure
 * @containing_type: the type this member is within
 * @member: the name of this member within the structure.
 *
 * Given a pointer to a member of a structure, this macro does
 * typechecking and figures out the offset to the enclosing type.
 *
 * Example:
 *	struct foo {
 *		int fielda, fieldb;
 *		// ...
 *	};
 *	struct info {
 *		int some_other_field;
 *		struct foo my_foo;
 *	};
 *
 *	static struct info *foo_to_info(struct foo *foo)
 *	{
 *		size_t off = container_off(struct info, my_foo);
 *		return (void *)((char *)foo - off);
 *	}
 */
#define container_off(containing_type, member)	\
	offsetof(containing_type, member)

/**
 * container_of_var - get pointer to enclosing structure using a variable
 * @member_ptr: pointer to the structure member
 * @container_var: a pointer of same type as this member's container
 * @member: the name of this member within the structure.
 *
 * Given a pointer to a member of a structure, this macro does pointer
 * subtraction to return the pointer to the enclosing type.
 *
 * Example:
 *	static struct info *foo_to_i(struct foo *foo)
 *	{
 *		struct info *i = container_of_var(foo, i, my_foo);
 *		return i;
 *	}
 */
#if HAVE_TYPEOF
#define container_of_var(member_ptr, container_var, member) \
	container_of(member_ptr, typeof(*container_var), member)
#else
#define container_of_var(member_ptr, container_var, member)	\
	((void *)((char *)(member_ptr)	-			\
		  container_off_var(container_var, member)))
#endif

/**
 * container_off_var - get offset of a field in enclosing structure
 * @container_var: a pointer to a container structure
 * @member: the name of a member within the structure.
 *
 * Given (any) pointer to a structure and a its member name, this
 * macro does pointer subtraction to return offset of member in a
 * structure memory layout.
 *
 */
#if HAVE_TYPEOF
#define container_off_var(var, member)		\
	container_off(typeof(*var), member)
#else
#define container_off_var(var, member)			\
	((const char *)&(var)->member - (const char *)(var))
#endif

#endif /* CCAN_CONTAINER_OF_H */
